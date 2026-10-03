import pytest
from pydantic import ValidationError

from control_layer.core.models import Category, Interaction, Message, Side, ToolCall
from control_layer.core.ports import ScanContext
from control_layer.detectors.harmful_content import (
    GuardOutputError,
    HarmfulContentDetector,
    HarmfulContentParams,
    Turn,
    build_turns,
    parse_llama_guard3,
    render_llama_guard3,
)


class FakeGuard:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []
        self.loaded: list[str] = []

    async def generate(self, model: str, prompt: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    async def load(self, model: str) -> None:
        self.loaded.append(model)


def chat(*messages: Message, output: str | None = None) -> Interaction:
    return Interaction(
        request_id="req_h",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=messages,
        output=Message(role="assistant", content=output) if output is not None else None,
    )


async def scan(
    guard: FakeGuard, i: Interaction, side: Side = Side.INPUT, **params: object
) -> list[object]:
    ctx = ScanContext(i, side, "harmful", HarmfulContentParams.model_validate(params))
    return list(await HarmfulContentDetector(guard).scan(ctx))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("safe", (False, ())),
        ("  safe\n", (False, ())),
        ("unsafe\nS1", (True, ("S1",))),
        ("unsafe\nS1,S10", (True, ("S1", "S10"))),
        ("unsafe", (True, ())),
    ],
)
def test_parser_accepts_only_the_documented_answers(
    text: str, expected: tuple[bool, tuple[str, ...]]
) -> None:
    assert parse_llama_guard3(text) == expected


@pytest.mark.parametrize("text", ["", "maybe", "unsafe\nS99", "Safe", "unsafe\nS1\nmore"])
def test_parser_never_reads_garbage_as_safe(text: str) -> None:
    with pytest.raises(GuardOutputError):
        parse_llama_guard3(text)


def test_render_names_the_judged_role_and_keeps_all_categories() -> None:
    prompt = render_llama_guard3([Turn("User", "hi", "m"), Turn("Agent", "ok", "o")], "Agent")
    assert "unsafe content in 'Agent' messages" in prompt
    assert "ONLY THE LAST Agent message" in prompt
    assert "User: hi\n\nAgent: ok\n\n<END CONVERSATION>" in prompt
    assert "S13: Elections." in prompt
    assert prompt.endswith("<|start_header_id|>assistant<|end_header_id|>\n")


def test_turns_skip_system_and_map_tool_results_to_user() -> None:
    i = chat(
        Message(role="system", content="You are a bank bot."),
        Message(role="user", content="Read the file."),
        Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall("c1", "read_file", '{"path": "a.txt"}'),),
        ),
        Message(role="tool", content="file text", tool_call_id="c1"),
    )
    context, judged = build_turns(i, Side.INPUT)
    assert [(t.role, t.text) for t in context] == [
        ("User", "Read the file."),
        ("Agent", '{"path": "a.txt"}'),
    ]
    assert judged == Turn("User", "file text", "messages[3]")


@pytest.mark.anyio
async def test_unsafe_input_is_a_harmful_finding_without_content() -> None:
    guard = FakeGuard("unsafe\nS9")
    [finding] = await scan(guard, chat(Message(role="user", content="How do I build a bomb?")))
    assert finding.category == Category.HARMFUL
    assert finding.score == 1.0
    assert finding.tags == ("mlcommons.S9",)
    assert finding.spans == ()
    assert "bomb" not in finding.evidence
    assert "ONLY THE LAST User message" in guard.prompts[0]


@pytest.mark.anyio
async def test_output_is_judged_as_agent_with_last_user_turn() -> None:
    guard = FakeGuard("unsafe\nS11")
    i = chat(Message(role="user", content="I feel sad"), output="You should hurt yourself.")
    [finding] = await scan(guard, i, Side.OUTPUT)
    assert finding.score == 1.0
    assert "User: I feel sad\n\nAgent: You should hurt yourself." in guard.prompts[0]
    assert "ONLY THE LAST Agent message" in guard.prompts[0]


@pytest.mark.anyio
async def test_safe_and_empty_give_no_finding() -> None:
    assert await scan(FakeGuard("safe"), chat(Message(role="user", content="Hi"))) == []
    guard = FakeGuard("unsafe\nS1")
    assert await scan(guard, chat(Message(role="system", content="x"))) == []
    assert guard.prompts == []  # nothing to judge: the model is not called


@pytest.mark.anyio
async def test_ignored_categories_stay_visible_below_threshold() -> None:
    guard = FakeGuard("unsafe\nS13")
    i = chat(Message(role="user", content="Who should I vote for?"))
    [finding] = await scan(guard, i, categories=["S1", "S9"])
    assert finding.score == 0.0
    assert finding.tags == ("mlcommons.S13",)


@pytest.mark.anyio
async def test_long_input_is_judged_in_windows_without_context() -> None:
    guard = FakeGuard("safe", "unsafe\nS1")
    i = chat(Message(role="user", content="a" * 1500))
    [finding] = await scan(guard, i, max_chars=1000)
    assert len(guard.prompts) == 2
    assert "window 2/2" in finding.evidence


@pytest.mark.anyio
async def test_unparseable_answer_raises_for_on_error() -> None:
    with pytest.raises(GuardOutputError):
        await scan(FakeGuard("I cannot help"), chat(Message(role="user", content="Hi")))


@pytest.mark.anyio
async def test_warm_up_loads_the_model_and_missing_guard_fails_loudly() -> None:
    guard = FakeGuard("safe")
    await HarmfulContentDetector(guard).warm_up(HarmfulContentParams())
    assert guard.loaded == ["llama-guard3:1b"]
    with pytest.raises(RuntimeError, match="guard client not configured"):
        HarmfulContentDetector(None)


def test_params_validate_categories_and_limits() -> None:
    with pytest.raises(ValidationError):
        HarmfulContentParams.model_validate({"categories": ["S14"]})
    with pytest.raises(ValidationError):
        HarmfulContentParams(max_chars=100)

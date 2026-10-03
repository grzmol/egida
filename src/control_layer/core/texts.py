"""The single place that knows where text lives inside an Interaction.

Detectors iterate `iter_texts()` instead of walking the structure; the pipeline applies redactions
with `apply_redactions()`. Targets are stable string paths used in `Span.target`.
"""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from control_layer.core.models import Interaction, Message, Side, Span, ToolCall, ToolDef

__all__ = ["Scope", "ScopedText", "apply_redactions", "iter_scoped_texts", "iter_texts"]

# Where a text sits, in the vocabulary of the signature feed (research 04 §5).
Scope = Literal[
    "input", "output", "tool_definition", "tool_call.args", "tool_result", "model_ref", "artifact"
]


@dataclass(frozen=True, slots=True)
class ScopedText:
    scope: Scope
    target: str
    text: str
    redactable: bool  # False for texts apply_redactions cannot rewrite (model, tool parameters)


_MESSAGE_CONTENT = re.compile(r"messages\[(\d+)\]\.content")
_MESSAGE_ARGS = re.compile(r"messages\[(\d+)\]\.tool_calls\[(\d+)\]\.arguments")
_TOOL_DESCRIPTION = re.compile(r"tools\[(\d+)\]\.description")
_OUTPUT_CONTENT = "output.content"
_OUTPUT_ARGS = re.compile(r"output\.tool_calls\[(\d+)\]\.arguments")


def iter_texts(interaction: Interaction, side: Side) -> Iterator[tuple[str, str]]:
    """Yield (target, text) pairs for one side of the interaction.

    INPUT: every message content (all roles, incl. system and tool), every tool call argument
    in the history, every tool description. OUTPUT: model output content and its tool calls.
    """
    if side is Side.INPUT:
        for i, message in enumerate(interaction.messages):
            yield f"messages[{i}].content", message.content
            for j, call in enumerate(message.tool_calls):
                yield f"messages[{i}].tool_calls[{j}].arguments", call.arguments
        for k, tool in enumerate(interaction.tools):
            yield f"tools[{k}].description", tool.description
        return
    output = interaction.output
    if output is None:
        return
    yield _OUTPUT_CONTENT, output.content
    for j, call in enumerate(output.tool_calls):
        yield f"output.tool_calls[{j}].arguments", call.arguments


def iter_scoped_texts(interaction: Interaction, side: Side) -> Iterator[ScopedText]:
    """Everything iter_texts yields, classified by feed scope, plus two read-only texts on INPUT:
    tool parameter schemas and the model reference. `artifact` has no source in proxy traffic."""
    for target, text in iter_texts(interaction, side):
        yield ScopedText(_scope_of(interaction, target), target, text, redactable=True)
    if side is Side.INPUT:
        for k, tool in enumerate(interaction.tools):
            yield ScopedText(
                "tool_definition", f"tools[{k}].parameters_json", tool.parameters_json, False
            )
        yield ScopedText("model_ref", "model", interaction.model, redactable=False)


def _scope_of(interaction: Interaction, target: str) -> Scope:
    if m := _MESSAGE_CONTENT.fullmatch(target):
        return "tool_result" if interaction.messages[int(m[1])].role == "tool" else "input"
    if _MESSAGE_ARGS.fullmatch(target) or _OUTPUT_ARGS.fullmatch(target):
        return "tool_call.args"
    if _TOOL_DESCRIPTION.fullmatch(target):
        return "tool_definition"
    if target == _OUTPUT_CONTENT:
        return "output"
    raise ValueError(f"unknown text target: {target!r}")


def apply_redactions(
    interaction: Interaction, spans: Sequence[Span], mask: str = "[REDACTED:{label}]"
) -> Interaction:
    """Return a new Interaction with every span replaced by `mask`.

    Overlapping or touching spans on the same target are merged (label of the first span wins).
    Unknown targets or spans outside the text raise ValueError.
    """
    by_target: dict[str, list[Span]] = defaultdict(list)
    for span in spans:
        by_target[span.target].append(span)

    result = interaction
    for target, target_spans in by_target.items():
        text = _get_text(result, target)
        for span in target_spans:
            if not 0 <= span.start < span.end <= len(text):
                raise ValueError(
                    f"span [{span.start}, {span.end}) outside text of {target} (len {len(text)})"
                )
        result = _set_text(result, target, _redact(text, target_spans, mask))
    return result


def _redact(text: str, spans: list[Span], mask: str) -> str:
    merged: list[tuple[int, int, str]] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        if merged and span.start <= merged[-1][1]:
            start, end, label = merged[-1]
            merged[-1] = (start, max(end, span.end), label)
        else:
            merged.append((span.start, span.end, span.label))
    for start, end, label in reversed(merged):
        text = text[:start] + mask.format(label=label) + text[end:]
    return text


def _get_text(interaction: Interaction, target: str) -> str:
    if m := _MESSAGE_CONTENT.fullmatch(target):
        return _message(interaction, int(m[1])).content
    if m := _MESSAGE_ARGS.fullmatch(target):
        return _call(_message(interaction, int(m[1])), int(m[2]), target).arguments
    if m := _TOOL_DESCRIPTION.fullmatch(target):
        return _tool(interaction, int(m[1])).description
    if target == _OUTPUT_CONTENT:
        return _output(interaction).content
    if m := _OUTPUT_ARGS.fullmatch(target):
        return _call(_output(interaction), int(m[1]), target).arguments
    raise ValueError(f"unknown text target: {target!r}")


def _set_text(interaction: Interaction, target: str, text: str) -> Interaction:
    if m := _MESSAGE_CONTENT.fullmatch(target):
        i = int(m[1])
        message = dataclasses.replace(_message(interaction, i), content=text)
        return _replace_message(interaction, i, message)
    if m := _MESSAGE_ARGS.fullmatch(target):
        i, j = int(m[1]), int(m[2])
        message = _with_call_args(_message(interaction, i), j, text, target)
        return _replace_message(interaction, i, message)
    if m := _TOOL_DESCRIPTION.fullmatch(target):
        k = int(m[1])
        tools = list(interaction.tools)
        tools[k] = dataclasses.replace(_tool(interaction, k), description=text)
        return dataclasses.replace(interaction, tools=tuple(tools))
    if target == _OUTPUT_CONTENT:
        output = dataclasses.replace(_output(interaction), content=text)
        return dataclasses.replace(interaction, output=output)
    if m := _OUTPUT_ARGS.fullmatch(target):
        output = _with_call_args(_output(interaction), int(m[1]), text, target)
        return dataclasses.replace(interaction, output=output)
    raise ValueError(f"unknown text target: {target!r}")


def _message(interaction: Interaction, index: int) -> Message:
    if index >= len(interaction.messages):
        raise ValueError(f"no message at index {index}")
    return interaction.messages[index]


def _tool(interaction: Interaction, index: int) -> ToolDef:
    if index >= len(interaction.tools):
        raise ValueError(f"no tool at index {index}")
    return interaction.tools[index]


def _output(interaction: Interaction) -> Message:
    if interaction.output is None:
        raise ValueError("interaction has no output")
    return interaction.output


def _call(message: Message, index: int, target: str) -> ToolCall:
    if index >= len(message.tool_calls):
        raise ValueError(f"no tool call for {target}")
    return message.tool_calls[index]


def _with_call_args(message: Message, index: int, text: str, target: str) -> Message:
    calls = list(message.tool_calls)
    calls[index] = dataclasses.replace(_call(message, index, target), arguments=text)
    return dataclasses.replace(message, tool_calls=tuple(calls))


def _replace_message(interaction: Interaction, index: int, message: Message) -> Interaction:
    messages = list(interaction.messages)
    messages[index] = message
    return dataclasses.replace(interaction, messages=tuple(messages))

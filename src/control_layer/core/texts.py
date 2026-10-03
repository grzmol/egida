"""The single place that knows where text lives inside an Interaction.

Detectors iterate `iter_texts()` instead of walking the structure; the pipeline applies redactions
with `apply_redactions()`. Targets are stable string paths used in `Span.target`.
"""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence

from control_layer.core.models import Interaction, Message, Side, Span, ToolCall, ToolDef

__all__ = ["apply_redactions", "iter_texts"]

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

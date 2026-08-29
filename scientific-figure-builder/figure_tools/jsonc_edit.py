"""Comment-preserving structural edits for the OpenCode JSONC config."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Token:
    kind: str
    start: int
    end: int
    value: str | None = None


@dataclass(frozen=True)
class Member:
    key: str
    key_start: int
    value_start: int
    value_end: int
    comma_start: int | None
    comma_end: int | None
    value_node: "ObjectNode | None"


@dataclass(frozen=True)
class ObjectNode:
    start: int
    close_start: int
    end: int
    members: tuple[Member, ...]

    def member(self, key: str) -> Member | None:
        return next((item for item in self.members if item.key == key), None)


def _tokens(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated JSONC block comment")
            index = end + 2
            continue
        if char == '"':
            start = index
            index += 1
            escaped = False
            while index < len(text):
                current = text[index]
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    index += 1
                    raw = text[start:index]
                    tokens.append(Token("string", start, index, json.loads(raw)))
                    break
                index += 1
            else:
                raise ValueError("unterminated JSONC string")
            continue
        if char in "{}[]:,":
            tokens.append(Token(char, index, index + 1, char))
            index += 1
            continue
        start = index
        while index < len(text):
            if text[index].isspace() or text[index] in "{}[]:,":
                break
            if text.startswith("//", index) or text.startswith("/*", index):
                break
            index += 1
        if start == index:
            raise ValueError(f"invalid JSONC token at character {index}")
        tokens.append(Token("literal", start, index, text[start:index]))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens

    def document(self) -> ObjectNode:
        if not self.tokens:
            raise ValueError("empty JSONC document")
        next_index, node = self.value(0)
        if next_index != len(self.tokens) or node is None:
            raise ValueError("OpenCode config must contain one root object")
        return node

    def value(self, index: int) -> tuple[int, ObjectNode | None]:
        if index >= len(self.tokens):
            raise ValueError("missing JSONC value")
        token = self.tokens[index]
        if token.kind == "{":
            return self.object(index)
        if token.kind == "[":
            return self.array(index)
        if token.kind in {"string", "literal"}:
            return index + 1, None
        raise ValueError(f"invalid JSONC value at character {token.start}")

    def object(self, index: int) -> tuple[int, ObjectNode]:
        opening = self.tokens[index]
        index += 1
        members: list[Member] = []
        while index < len(self.tokens) and self.tokens[index].kind != "}":
            key = self.tokens[index]
            if key.kind != "string":
                raise ValueError(f"JSONC object key must be a string at {key.start}")
            index += 1
            if index >= len(self.tokens) or self.tokens[index].kind != ":":
                raise ValueError(f"missing colon after JSONC key at {key.start}")
            index += 1
            if index >= len(self.tokens):
                raise ValueError(f"missing value for JSONC key {key.value!r}")
            value_start = self.tokens[index].start
            index, value_node = self.value(index)
            value_end = self.tokens[index - 1].end
            comma_start = comma_end = None
            if index < len(self.tokens) and self.tokens[index].kind == ",":
                comma_start = self.tokens[index].start
                comma_end = self.tokens[index].end
                index += 1
            elif index < len(self.tokens) and self.tokens[index].kind != "}":
                raise ValueError(f"missing comma after JSONC key {key.value!r}")
            if any(item.key == key.value for item in members):
                raise ValueError(f"duplicate JSONC object key: {key.value!r}")
            members.append(Member(
                key=str(key.value),
                key_start=key.start,
                value_start=value_start,
                value_end=value_end,
                comma_start=comma_start,
                comma_end=comma_end,
                value_node=value_node,
            ))
        if index >= len(self.tokens) or self.tokens[index].kind != "}":
            raise ValueError(f"unterminated JSONC object at {opening.start}")
        closing = self.tokens[index]
        return index + 1, ObjectNode(
            start=opening.start,
            close_start=closing.start,
            end=closing.end,
            members=tuple(members),
        )

    def array(self, index: int) -> tuple[int, None]:
        opening = self.tokens[index]
        index += 1
        while index < len(self.tokens) and self.tokens[index].kind != "]":
            index, _ = self.value(index)
            if index < len(self.tokens) and self.tokens[index].kind == ",":
                index += 1
            elif index < len(self.tokens) and self.tokens[index].kind != "]":
                raise ValueError(f"missing comma in JSONC array at {opening.start}")
        if index >= len(self.tokens) or self.tokens[index].kind != "]":
            raise ValueError(f"unterminated JSONC array at {opening.start}")
        return index + 1, None


def _without_comments(text: str) -> str:
    output = list(text)
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
            for position in range(index, end):
                output[position] = " "
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated JSONC block comment")
            for position in range(index, end + 2):
                if output[position] not in "\r\n":
                    output[position] = " "
            index = end + 2
            continue
        index += 1
    return "".join(output)


def _without_trailing_commas(text: str) -> str:
    output = list(text)
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char != ",":
            continue
        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        if next_index < len(text) and text[next_index] in "}]":
            output[index] = " "
    return "".join(output)


def load_jsonc(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    _Parser(_tokens(text)).document()
    value = json.loads(_without_trailing_commas(_without_comments(text)))
    if not isinstance(value, dict):
        raise ValueError("OpenCode config must contain a root object")
    return value


def _root(text: str) -> ObjectNode:
    return _Parser(_tokens(text)).document()


def _line_indent(text: str, position: int) -> str:
    line_start = text.rfind("\n", 0, position) + 1
    prefix = text[line_start:position]
    return prefix if not prefix.strip() else "  "


def _render_value(value: Any, indent: str) -> str:
    lines = json.dumps(value, indent=2, ensure_ascii=False).splitlines()
    return lines[0] + "".join("\n" + indent + line for line in lines[1:])


def _insert_member(text: str, node: ObjectNode, key: str, value: Any) -> str:
    indent = (
        _line_indent(text, node.members[0].key_start)
        if node.members else _line_indent(text, node.close_start) + "  "
    )
    separator_edit = None
    if node.members and node.members[-1].comma_end is None:
        separator_edit = node.members[-1].value_end
    rendered = f'\n{indent}{json.dumps(key)}: {_render_value(value, indent)}'
    candidate = text[:node.close_start] + rendered + text[node.close_start:]
    if separator_edit is not None:
        candidate = candidate[:separator_edit] + "," + candidate[separator_edit:]
    return candidate


def _set_member(text: str, node: ObjectNode, key: str, value: Any) -> str:
    member = node.member(key)
    if member is None:
        return _insert_member(text, node, key, value)
    indent = _line_indent(text, member.key_start)
    rendered = _render_value(value, indent)
    return text[:member.value_start] + rendered + text[member.value_end:]


def set_mcp_entry(text: str, mcp_name: str, entry: dict[str, Any]) -> str:
    if not text.strip():
        text = "{}\n"
    data = load_jsonc(text)
    root = _root(text)
    if "$schema" not in data:
        text = _set_member(text, root, "$schema", "https://opencode.ai/config.json")
        data = load_jsonc(text)
        root = _root(text)
    mcp_member = root.member("mcp")
    if mcp_member is None:
        text = _set_member(text, root, "mcp", {mcp_name: entry})
    else:
        if mcp_member.value_node is None or not isinstance(data.get("mcp"), dict):
            raise ValueError("OpenCode config field 'mcp' must be an object")
        text = _set_member(text, mcp_member.value_node, mcp_name, entry)
    candidate = load_jsonc(text)
    if candidate.get("mcp", {}).get(mcp_name) != entry:
        raise RuntimeError("OpenCode MCP candidate was not rendered correctly")
    return text


def _remove_member(text: str, node: ObjectNode, member: Member) -> str:
    index = node.members.index(member)
    if member.comma_end is not None:
        start, end = member.key_start, member.comma_end
    else:
        start, end = member.key_start, member.value_end
    return text[:start] + text[end:]


def remove_mcp_entry(text: str, mcp_name: str) -> tuple[str, bool]:
    if not text.strip():
        return text, False
    data = load_jsonc(text)
    root = _root(text)
    mcp_member = root.member("mcp")
    if (
        mcp_member is None
        or mcp_member.value_node is None
        or not isinstance(data.get("mcp"), dict)
    ):
        return text, False
    target = mcp_member.value_node.member(mcp_name)
    if target is None:
        return text, False
    candidate = _remove_member(text, mcp_member.value_node, target)
    parsed = load_jsonc(candidate)
    if mcp_name in parsed.get("mcp", {}):
        raise RuntimeError("OpenCode MCP entry was not removed")
    return candidate, True


__all__ = ["load_jsonc", "remove_mcp_entry", "set_mcp_entry"]

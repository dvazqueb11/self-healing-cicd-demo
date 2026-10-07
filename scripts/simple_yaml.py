"""A tiny, dependency-free loader for the restricted YAML subset used by
`.github/policies/self-heal-policy.yml`.

This is NOT a general-purpose YAML parser. It intentionally supports only
the constructs this repository's policy file uses:

  - top-level and nested mappings (`key:` / `key: value`)
  - 2-space indentation
  - lists of scalar items (`- value`)
  - double-quoted, single-quoted, and bare scalars
  - integers and floats
  - `#` line comments (only at the start of a token, not inside quotes)
  - blank lines

Keeping policy parsing dependency-free avoids a third-party YAML library
requirement for a single small configuration file, and keeps the parser's
behavior fully auditable alongside the policy it reads.
"""
from __future__ import annotations

from typing import Any, List, Tuple


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _parse_scalar(token: str) -> Any:
    token = token.strip()
    if token == "" or token == "~":
        return None
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        return token[1:-1]
    if token in ("true", "True"):
        return True
    if token in ("false", "False"):
        return False
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def load(text: str) -> Any:
    raw_lines = text.split("\n")
    lines: List[Tuple[int, str]] = []
    for raw in raw_lines:
        stripped = _strip_comment(raw).rstrip()
        if stripped.strip() == "":
            continue
        lines.append((_indent_of(stripped), stripped.strip()))

    pos = 0

    def parse_block(indent: int) -> Any:
        nonlocal pos
        is_list = pos < len(lines) and lines[pos][1].startswith("- ") or (
            pos < len(lines) and lines[pos][1] == "-"
        )
        result: Any = [] if is_list else {}

        while pos < len(lines):
            cur_indent, content = lines[pos]
            if cur_indent < indent:
                break
            if cur_indent > indent:
                # Should not happen if callers manage indent correctly.
                break

            if content.startswith("- "):
                value_token = content[2:]
                pos += 1
                if value_token == "":
                    result.append(parse_block(indent + 2))
                else:
                    result.append(_parse_scalar(value_token))
                continue
            if content == "-":
                pos += 1
                result.append(parse_block(indent + 2))
                continue

            if ":" not in content:
                raise ValueError(f"Cannot parse policy line: {content!r}")
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            pos += 1

            if value == "":
                # Nested block: a mapping or a list, indented further.
                if pos < len(lines) and lines[pos][0] > indent:
                    result[key] = parse_block(lines[pos][0])
                else:
                    result[key] = None
            else:
                result[key] = _parse_scalar(value)

        return result

    return parse_block(0)


def load_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return load(handle.read())

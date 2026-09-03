"""Tests for the frontmatter splitter and its small parser."""

from __future__ import annotations

from mli.frontmatter import body_only, parse_fields, split_frontmatter

DOC = """\
---
name: use-thing
description: "Look things up."
---

# Body

text
"""


def test_split_is_lossless() -> None:
    front, body = split_frontmatter(DOC)
    assert front is not None
    assert front.raw + body == DOC
    assert front.raw.startswith("---\n") and front.raw.endswith("---\n")
    assert body.startswith("\n# Body")


def test_fields_are_parsed_and_quotes_stripped() -> None:
    front, _ = split_frontmatter(DOC)
    assert front is not None
    assert front.get("name") == "use-thing"
    assert front.get("description") == "Look things up."
    assert front.get("missing") is None
    assert front.get("missing", "x") == "x"


def test_no_frontmatter_returns_text_verbatim() -> None:
    text = "# Just a body\n\n---\n\nnot a fence\n"
    assert split_frontmatter(text) == (None, text)
    assert body_only(text) == text


def test_unclosed_block_is_not_frontmatter() -> None:
    text = "---\nname: x\n\n# body\n"
    assert split_frontmatter(text) == (None, text)


def test_empty_text() -> None:
    assert split_frontmatter("") == (None, "")


def test_folded_and_literal_block_scalars() -> None:
    lines = [
        "name: agent\n",
        "description: >\n",
        "  First line of a long\n",
        "  description.\n",
        "\n",
        "  Second paragraph.\n",
        "notes: |\n",
        "  line one\n",
        "  line two\n",
        "tools: Read, Grep\n",
    ]
    fields = parse_fields(lines)
    assert (
        fields["description"] == "First line of a long description. Second paragraph."
    )
    assert fields["notes"] == "line one\nline two"
    assert fields["tools"] == "Read, Grep"


def test_comments_and_nested_mappings_are_ignored() -> None:
    lines = ["# comment\n", "top: value\n", "nested:\n", "  child: 1\n", "after: ok\n"]
    fields = parse_fields(lines)
    assert fields == {"top": "value", "nested": "", "after": "ok"}


def test_colons_in_values_survive() -> None:
    fields = parse_fields(["url: https://example.com/a:b\n"])
    assert fields["url"] == "https://example.com/a:b"

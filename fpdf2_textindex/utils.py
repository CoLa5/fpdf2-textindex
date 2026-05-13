"""Utils."""

# ruff: noqa: D103

import re


def escape_square_brackets(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


def insert_at_match(
    text: str,
    match: re.Match[str],
    insert: str,
    offset: int = 0,
) -> str:
    return (
        text[: match.start() + offset] + insert + text[match.end() + offset :]
    )


def md_link(link_text: str | None, link: str) -> str:
    link_text = escape_square_brackets(link_text or "")
    return f"[{link_text:s}]({link:s})"


def remove_match_from_str(
    text: str,
    match: re.Match[str],
    offset: int = 0,
) -> str:
    return text[: match.start() + offset] + text[match.end() + offset :]


def remove_quotes(text: str) -> str:
    return text.strip(" '\"")

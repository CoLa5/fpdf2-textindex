"""Utils."""

# ruff: noqa: D103

from collections.abc import Iterable
import re

from fpdf2_textindex import constants as const


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


def join_label_path(label_path: Iterable[str]) -> str:
    return f" {const.PATH_DELIMITER:s} ".join(f'"{la:s}"' for la in label_path)


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


def split_label_path(label_path_str: str) -> list[str]:
    # Split label path and remove quotes from path elements
    return [
        remove_quotes(la) for la in label_path_str.split(const.PATH_DELIMITER)
    ]

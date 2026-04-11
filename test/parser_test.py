import logging
import pathlib

import pytest

from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.parser import TextIndexParser
from test.conftest import create_figure_test_cases

HERE = pathlib.Path(__file__).resolve().parent
CONCORDANCE_FILE: pathlib.Path = HERE / "concordance.tsv"


@pytest.mark.parametrize(
    ["msg", "text", "parsed_text", "entries", "warn_msg"],
    list(create_figure_test_cases()),
)
def test_parser(
    caplog: pytest.LogCaptureFixture,
    msg: str,
    text: str,
    parsed_text: str,
    entries: list[TextIndexEntry],
    warn_msg: str | None,
) -> None:
    parser = TextIndexParser()
    with caplog.at_level(logging.WARNING):
        new_text = parser.parse_text(text)

    assert new_text == parsed_text, msg
    assert len(parser.entries) == len(entries), msg
    for entry in entries:
        parsed_entry, existing = parser.entry_at_label_path(entry.label_path)
        assert existing, (entry, parser.entries, msg)
        assert isinstance(parsed_entry, TextIndexEntry), (
            entry,
            msg,
        )
        assert parsed_entry.label == entry.label, (entry, msg)
        assert parsed_entry.label_path == entry.label_path, (entry, msg)
        assert parsed_entry.references == entry.references, (entry, msg)
        assert parsed_entry.cross_references == entry.cross_references, (
            entry,
            msg,
        )
        assert parsed_entry.sort_key == entry.sort_key, (entry, msg)

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    if warnings or warn_msg:
        assert warn_msg is not None and any(
            warn_msg in r.message for r in warnings
        ), (msg, warn_msg)

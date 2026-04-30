import logging

import pytest

from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.parser import TextIndexParser
from test.conftest import create_figure_test_cases


@pytest.mark.parametrize(
    ("msg", "text", "parsed_text", "entries", "warn_msg"),
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
        assert isinstance(parsed_entry, TextIndexEntry), (entry, msg)
        assert parsed_entry.label == entry.label, (entry, msg)
        assert parsed_entry.label_path == entry.label_path, (entry, msg)
        assert parsed_entry.references == entry.references, (entry, msg)
        assert parsed_entry.cross_references == entry.cross_references, (
            entry,
            msg,
        )
        assert parsed_entry.sort_key == entry.sort_key, (entry, msg)

    cap_warn_msgs = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    if cap_warn_msgs or warn_msg:
        assert warn_msg in cap_warn_msgs, (msg, warn_msg, cap_warn_msgs)

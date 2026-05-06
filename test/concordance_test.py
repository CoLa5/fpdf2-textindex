from collections.abc import Iterator
import logging
import pathlib

import pytest

from fpdf2_textindex.concordance import ConcordanceList
from fpdf2_textindex.interface import CrossReferenceType
from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.parser import TextIndexParser
from test.conftest import DATA

CONCORDANCE_FILE: pathlib.Path = DATA / "concordance.tsv"


def test_sequence() -> None:
    cparser = ConcordanceList.from_file(CONCORDANCE_FILE)
    assert len(cparser) == 7
    for pattern, replacement in iter(cparser):
        assert isinstance(pattern, str)
        assert isinstance(replacement, str)
    for i in range(len(cparser)):
        assert isinstance(cparser[i], tuple)
        assert len(cparser[i]) == 2
        pattern, replacement = cparser[i]
        assert isinstance(pattern, str)
        assert isinstance(replacement, str)
    for pattern, replacement in cparser[1:3]:
        assert isinstance(pattern, str)
        assert isinstance(replacement, str)


def test_empty_file(tmp_path: pathlib.Path) -> None:
    file = tmp_path / "concordance.tsv"
    with file.open(mode="w") as f:
        f.write("\n")
    cparser = ConcordanceList.from_file(file)
    assert len(cparser) == 0


def test_invalid_file() -> None:
    with pytest.raises(OSError):  # noqa: PT011
        ConcordanceList.from_file("invalid_file")


@pytest.mark.parametrize(
    ("text", "parsed_text"),
    [
        (
            "Single-tap iPad or double-tapped ipad lead to simultaneous layer "
            "configs without combo{^}, firmware{^} and chords{^}.",
            '[Single-tap]{^tap} [iPad]{^"Apple platforms"} or '
            "[double-tapped]{^tap} ipad lead to [simultaneous]{^|combo;+chord} "
            "[layer]{^toggle>layer} [configs]{^|firmware} without combo{^}, "
            "firmware{^} and chords{^}.",
        )
    ],
)
def test_parse_text(
    text: str,
    parsed_text: str,
) -> None:
    cparser = ConcordanceList.from_file(CONCORDANCE_FILE)
    new_text = cparser.parse_text(text)
    assert new_text == parsed_text


def create_concordance_test_cases() -> Iterator[
    str,
    str,
    str,
    list[TextIndexEntry],
    str | None,
]:
    test_case = "Concordance list"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="tap", parent=root)]
    entries[-1].add_reference(0)
    entries[-1].add_reference(2)
    entries.append(TextIndexEntry(label="Apple platforms", parent=root))
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="simultaneous", parent=root))
    entries[-1].add_cross_reference(3, CrossReferenceType.SEE, ["combo"])
    entries[-1].add_cross_reference(3, CrossReferenceType.ALSO, ["chord"])
    entries.append(TextIndexEntry(label="toggle", parent=root))
    entries.append(TextIndexEntry(label="layer", parent=entries[-1]))
    entries[-1].add_reference(4)
    entries.append(TextIndexEntry(label="configs", parent=root))
    entries[-1].add_cross_reference(5, CrossReferenceType.SEE, ["firmware"])
    entries.append(TextIndexEntry(label="combo", parent=root))
    entries[-1].add_reference(6)
    entries.append(TextIndexEntry(label="firmware", parent=root))
    entries[-1].add_reference(7)
    entries.append(TextIndexEntry(label="chords", parent=root))
    entries[-1].add_reference(8)
    yield (
        test_case,
        "Single-tap iPad or double-tapped ipad lead to simultaneous layer "
        "configs without combo{^}, firmware{^} and chords{^}.",
        "[Single-tap](#idx0) [iPad](#idx1) or [double-tapped](#idx2) ipad lead "
        "to [simultaneous](#idx3) [layer](#idx4) [configs](#idx5) without "
        "[combo](#idx6), [firmware](#idx7) and [chords](#idx8).",
        entries,
        None,
    )


@pytest.mark.parametrize(
    ("msg", "text", "parsed_text", "entries", "warn_msg"),
    list(create_concordance_test_cases()),
)
def test_parser_with_concordance(
    caplog: pytest.LogCaptureFixture,
    msg: str,
    text: str,
    parsed_text: str,
    entries: list[TextIndexEntry],
    warn_msg: str | None,
) -> None:
    cparser = ConcordanceList.from_file(CONCORDANCE_FILE)
    tparser = TextIndexParser()

    with caplog.at_level(logging.WARNING):
        new_text = cparser.parse_text(text)
        new_text = tparser.parse_text(new_text)

    assert new_text == parsed_text, msg
    assert len(tparser.entries) == len(entries), msg
    for entry in entries:
        parsed_entry, existing = tparser.entry_at_label_path(entry.label_path)
        assert existing, (entry, tparser.entries, msg)
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

    cap_warn_msgs = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    if cap_warn_msgs or warn_msg:
        assert warn_msg is not None, (msg, warn_msg, cap_warn_msgs)
        assert warn_msg in cap_warn_msgs, (msg, warn_msg, cap_warn_msgs)

from collections.abc import Iterable, Iterator
import datetime as dt
import hashlib
import pathlib
import shutil
import subprocess
from typing import Final
import warnings
import zlib

import fpdf
import pytest

from fpdf2_textindex.interface import CrossReferenceType
from fpdf2_textindex.interface import TextIndexEntry

HERE: pathlib.Path = pathlib.Path(__file__).resolve().parent
DATA: pathlib.Path = HERE / "data"

EPOCH: dt.datetime = dt.datetime(1969, 12, 31, 19, 00, 00).replace(
    tzinfo=dt.timezone.utc
)

QPDF_AVAILABLE: Final[bool] = bool(shutil.which("qpdf"))
if not QPDF_AVAILABLE:
    warnings.warn(
        "qpdf command not available on the $PATH, falling back to hash-based "
        "comparisons in tests",
        stacklevel=1,
    )

USING_ZLIB_NG: Final[bool] = (
    hasattr(zlib, "ZLIBNG_VERSION")
    or "zlib-ng" in getattr(zlib, "ZLIB_RUNTIME_VERSION", "").lower()
    or "zlib-ng" in getattr(zlib, "ZLIB_VERSION", "").lower()
)


def _qpdf(input_pdf_filepath: pathlib.Path) -> bytes:
    return _run_cmd(
        "qpdf",
        "--deterministic-id",
        "--password=fpdf2",
        "--qdf",
        str(input_pdf_filepath),
        "-",
    )


def _run_cmd(*args: str) -> bytes:
    try:
        return subprocess.check_output(args, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        print(f"\nqpdf STDERR: {error.stderr.decode().strip()}")
        raise


# NOTE: Adapted from [fpdf2-testing](https://github.com/py-pdf/fpdf2/blob/master/test/conftest.py)
def assert_pdf_equal(
    pdf: fpdf.FPDF,
    expected: fpdf.FPDF | bytearray | pathlib.Path,
    tmp_path: pathlib.Path,
    *,
    at_epoch: bool = True,
    generate: bool = False,
    ignore_id_changes: bool = False,
    ignore_original_obj_ids: bool = False,
    ignore_xref_offsets: bool = False,
    linearize: bool = False,
) -> None:
    """This compare the output of a `FPDF` instance (or `Template` instance),
    with the provided PDF file.

    The `CreationDate` of the newly generated PDF is fixed, so that it never
    triggers a diff.

    A hash-based comparison logic is used as a fallback.

    Args:
        pdf: Instance of :py:class:`fpdf.FPDF`. The :py:meth:`fpdf.FPDF.output`-
            method will be called on it.
        expected: Instance of :py:class:`fpdf.FPDF`, ``bytearray`` or file path
            to a PDF file matching the expected output.
        tmp_path: Temporary directory provided by :py:mod:`pytest` individually
            to the caller test function.
        generate: Only generate PDF-output to `rel_expected_pdf_filepath` and
            return. Useful to create new tests.
    """
    if at_epoch:
        pdf.creation_date = EPOCH
    if generate:
        assert isinstance(expected, pathlib.Path), (
            "When passing `True` to `generate`"
            "a pathlib.Path must be provided as the `expected` parameter"
        )
        pdf.output(expected.open("wb"), linearize=linearize)
        return

    # Force ignore_id_changes when Python is linked against zlib-ng,
    # as the compressed data is not 100% identical to standard zlib.
    # https://github.com/python/cpython/pull/131438
    if USING_ZLIB_NG and QPDF_AVAILABLE:
        ignore_id_changes = True

    if isinstance(expected, pathlib.Path):
        expected_pdf_path = expected
    else:
        expected_pdf_path = tmp_path / "expected.pdf"
        with expected_pdf_path.open("wb") as pdf_file:
            if isinstance(expected, (bytes | bytearray)):
                pdf_file.write(expected)
            else:
                expected.set_creation_date(EPOCH)
                expected.output(pdf_file, linearize=linearize)

    actual_pdf_path = tmp_path / "actual.pdf"
    with actual_pdf_path.open("wb") as pdf_file:
        pdf.output(pdf_file, linearize=linearize)

    if (
        QPDF_AVAILABLE
    ):  # Favor qpdf-based comparison, as it helps a lot debugging:
        actual_qpdf = _qpdf(actual_pdf_path)
        expected_qpdf = _qpdf(expected_pdf_path)
        (tmp_path / "actual_qpdf.pdf").write_bytes(actual_qpdf)
        (tmp_path / "expected_qpdf.pdf").write_bytes(expected_qpdf)
        actual_lines = actual_qpdf.splitlines()
        expected_lines = expected_qpdf.splitlines()
        if ignore_id_changes:
            actual_lines = filter_out_doc_id(actual_lines)
            expected_lines = filter_out_doc_id(expected_lines)
        if ignore_original_obj_ids:
            actual_lines = filter_out_original_obj_ids(actual_lines)
            expected_lines = filter_out_original_obj_ids(expected_lines)
        if ignore_xref_offsets:
            actual_lines = filter_out_xref_offsets(actual_lines)
            expected_lines = filter_out_xref_offsets(expected_lines)
        if actual_lines != expected_lines:
            # It is important to reduce the size of both list of bytes here,
            # to avoid .assertSequenceEqual to take forever to finish, that
            # itself calls difflib.ndiff, that has cubic complexity from this
            # comment by Tim Peters: https://bugs.python.org/issue6931#msg223459
            actual_lines = subst_streams_with_hashes(actual_lines)
            expected_lines = subst_streams_with_hashes(expected_lines)
        assert actual_lines == expected_lines
        if linearize:
            _run_cmd("qpdf", "--check-linearization", str(actual_pdf_path))
    else:  # Fallback to hash comparison
        actual_hash = hashlib.md5(actual_pdf_path.read_bytes()).hexdigest()
        expected_hash = hashlib.md5(expected_pdf_path.read_bytes()).hexdigest()

        assert actual_hash == expected_hash, f"{actual_hash} != {expected_hash}"


def filter_out_doc_id(lines: Iterable[bytes]) -> list[bytes]:
    return [line for line in lines if not line.startswith(b"  /ID [<")]


def filter_out_original_obj_ids(lines: Iterable[bytes]) -> list[bytes]:
    return [
        line
        for line in lines
        if not line.startswith(b"%% Original object ID: ")
    ]


def filter_out_xref_offsets(lines: Iterable[bytes]) -> list[bytes]:
    return [line for line in lines if not line.endswith(b" 00000 n ")]


def subst_streams_with_hashes(in_lines: Iterable[bytes]) -> list[bytes]:
    """This utility function reduce the length of `in_lines`, a list of bytes,
    by replacing multi-lines streams looking like this:

    ```
    stream
    {non-printable-binary-data}endstream
    ```

    by a single line with this format:

    ```
    <stream with MD5 hash: abcdef0123456789>
    ```
    """
    out_lines, stream = [], None
    for line in in_lines:
        if line == b"stream":
            assert stream is None
            stream = bytearray()
        elif stream == b"stream":
            # First line of stream, we check if it is binary or not:
            try:
                line.decode("latin-1")
                if not (b"\0" in line or b"\xff" in line):
                    # It's likely to be text! No need to compact stream
                    stream = None
            except UnicodeDecodeError:
                pass
        if stream is None:
            out_lines.append(line)
        else:
            stream += line
        if line.endswith(b"endstream") and stream:
            stream_hash = hashlib.md5(stream).hexdigest()
            out_lines.append(
                f"<stream with MD5 hash: {stream_hash}>\n".encode()
            )
            stream = None
    return out_lines


# NOTE: Adapted from https://mattgemmell.scot/textindex/
def create_figure_test_cases() -> Iterator[
    str,
    str,
    str,
    list[TextIndexEntry],
    str | None,
]:
    test_case = "Empty entry"
    yield (
        test_case,
        "{^}",
        "{^}",
        [],
        "No entry label specified in directive, ignoring: '{^}'",
    )

    test_case = "Marking entries"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="firmware", parent=root)]
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="key combinations", parent=root))
    entries[-1].add_reference(1)
    yield (
        test_case,
        "Most mechanical keyboard firmware{^} supports the use of "
        "[key combinations]{^}.",
        "Most mechanical keyboard [firmware](#idx0) supports the use of "
        "[key combinations](#idx1).",
        entries,
        None,
    )

    test_case = "Marking entries (ambiguities)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="firmware", parent=root)]
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="key combinations", parent=root))
    entries[-1].add_reference(1)
    yield (
        test_case,
        "Most mechanical keyboard [x]firmware{^} supports the use of "
        "x[key combinations]{^}.",
        "Most mechanical keyboard [x][firmware](#idx0) supports the use of "
        "x[key combinations](#idx1).",
        entries,
        None,
    )

    test_case = "Heading overrides"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="foo bar", parent=root)]
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="foo baz", parent=root))
    entries[-1].add_reference(1)
    yield (
        test_case,
        'This is a standalone mark: {^"foo bar"}and this one has an overridden '
        '[heading]{^"foo baz"}.',
        "This is a standalone mark: [](#idx0)and this one has an overridden "
        "[heading](#idx1).",
        entries,
        None,
    )

    test_case = "Nested headings (sub-entry)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="foo bar", parent=root)]
    entries.append(TextIndexEntry(label="baz", parent=entries[-1]))
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    yield (
        test_case,
        'This is a standalone nested mark: {^"foo bar">baz}and this one will '
        'create an identical entry: [baz]{^"foo bar">}.',
        "This is a standalone nested mark: [](#idx0)and this one will "
        "create an identical entry: [baz](#idx1).",
        entries,
        None,
    )

    test_case = "Nested headings (sub-sub-entry)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="foo bar", parent=root)]
    entries.append(TextIndexEntry(label="bay", parent=entries[-1]))
    entries.append(TextIndexEntry(label="baz", parent=entries[-1]))
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    yield (
        test_case,
        'This is a standalone nested mark: {^"foo bar">bay>baz}and this one '
        'will create an identical entry: [baz]{^"foo bar">bay>}.',
        "This is a standalone nested mark: [](#idx0)and this one will "
        "create an identical entry: [baz](#idx1).",
        entries,
        None,
    )

    test_case = "Emphasised and expanded headings"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="__emphasised__", parent=root)]
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="emphasised (nope)", parent=root))
    entries[-1].add_reference(2)
    yield (
        test_case,
        "This entry will be __emphasised__{^} in the index. "
        "This entry will be __[emphasised]{^}__ in the index, too. "
        'This expanded entry won\'t be __emphasised__{^"* (nope)"}.',
        "This entry will be __[emphasised](#idx0)__ in the index. "
        "This entry will be __[emphasised](#idx1)__ in the index, too. "
        "This expanded entry won't be __[emphasised](#idx2)__.",
        entries,
        None,
    )

    test_case = "Double emphasised and expanded headings"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="**__emphasised__**", parent=root)]
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="emphasised (nope)", parent=root))
    entries[-1].add_reference(2)
    yield (
        test_case,
        "This entry will be **__emphasised__**{^} in the index. "
        "This entry will be **__[emphasised]{^}__** in the index, too. "
        'This expanded entry won\'t be **__emphasised__**{^"* (nope)"}.',
        "This entry will be **__[emphasised](#idx0)__** in the index. "
        "This entry will be **__[emphasised](#idx1)__** in the index, too. "
        "This expanded entry won't be **__[emphasised](#idx2)__**.",
        entries,
        None,
    )

    test_case = "Nested emphasised headings (sub-entry)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="__foo bar__", parent=root)]
    entries.append(TextIndexEntry(label="**baz**", parent=entries[-1]))
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    yield (
        test_case,
        'This is a standalone nested mark: {^"__foo bar__">**baz**}and this '
        'one will create an identical entry: **[baz]{^"__foo bar__">}**.',
        "This is a standalone nested mark: [](#idx0)and this one will "
        "create an identical entry: **[baz](#idx1)**.",
        entries,
        None,
    )

    test_case = "Nested emphasised headings (sub-sub-entry)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="__foo bar__", parent=root)]
    entries.append(TextIndexEntry(label="--bay--", parent=entries[-1]))
    entries.append(TextIndexEntry(label="**baz**", parent=entries[-1]))
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    yield (
        test_case,
        'This is a standalone nested mark: {^"__foo bar__">--bay-->**baz**}and '
        "this one will create an identical entry: "
        '**[baz]{^"__foo bar__">--bay-->}**.',
        "This is a standalone nested mark: [](#idx0)and this one will "
        "create an identical entry: **[baz](#idx1)**.",
        entries,
        None,
    )

    test_case = "Emphasis-stripping with wildcards *"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="**bold**", parent=root)]
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="__italics__", parent=root))
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="--underline--", parent=root))
    entries[-1].add_reference(2)
    entries.append(TextIndexEntry(label="~~strikethrough~~", parent=root))
    entries[-1].add_reference(3)
    entries.append(TextIndexEntry(label="bold", parent=root))
    entries[-1].add_reference(4)
    entries.append(TextIndexEntry(label="italics", parent=root))
    entries[-1].add_reference(5)
    entries.append(TextIndexEntry(label="underline", parent=root))
    entries[-1].add_reference(6)
    entries.append(TextIndexEntry(label="strikethrough", parent=root))
    entries[-1].add_reference(7)
    yield (
        test_case,
        "This entry will be **bold**{^}, __italics__{^}, --underline--{^} or "
        "~~strikethrough~~{^}. This entry won't be **bold**{^*}, "
        "__italics__{^*}, --underline--{^*} or ~~strikethrough~~{^*}.",
        "This entry will be **[bold](#idx0)**, __[italics](#idx1)__, "
        "--[underline](#idx2)-- or ~~[strikethrough](#idx3)~~. This entry "
        "won't be **[bold](#idx4)**, __[italics](#idx5)__, "
        "--[underline](#idx6)-- or ~~[strikethrough](#idx7)~~.",
        entries,
        None,
    )

    test_case = "Emphasis-stripping and lower-case with double wildcards **"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="**bold**", parent=root)]
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="__italics__", parent=root))
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="--underline--", parent=root))
    entries[-1].add_reference(2)
    entries.append(TextIndexEntry(label="~~strikethrough~~", parent=root))
    entries[-1].add_reference(3)
    entries.append(TextIndexEntry(label="bold", parent=root))
    entries[-1].add_reference(4)
    entries.append(TextIndexEntry(label="italics", parent=root))
    entries[-1].add_reference(5)
    entries.append(TextIndexEntry(label="underline", parent=root))
    entries[-1].add_reference(6)
    entries.append(TextIndexEntry(label="strikethrough", parent=root))
    entries[-1].add_reference(7)
    yield (
        test_case,
        "This entry will be **bold**{^}, __italics__{^}, --underline--{^} or "
        "~~strikethrough~~{^}. This entry won't be **Bold**{^**}, "
        "__Italics__{^**}, --Underline--{^**} or ~~Strikethrough~~{^**}.",
        "This entry will be **[bold](#idx0)**, __[italics](#idx1)__, "
        "--[underline](#idx2)-- or ~~[strikethrough](#idx3)~~. This entry "
        "won't be **[Bold](#idx4)**, __[Italics](#idx5)__, "
        "--[Underline](#idx6)-- or ~~[Strikethrough](#idx7)~~.",
        entries,
        None,
    )

    test_case = "Prefix wildcards (^*^)"
    root = TextIndexEntry(label=None)
    entries = [
        TextIndexEntry(
            label="Churchill, Sir Winston Leonard Spencer",
            parent=root,
        )
    ]
    entries[-1].add_reference(0)
    entries[-1].add_reference(1)
    yield (
        test_case,
        "Sir Winston Leonard Spencer "
        'Churchill{^"*, Sir Winston Leonard Spencer"} was Prime Minister from '
        "1940 to 1945, and again from 1951 to 1955. Churchill{^*^} was born on "
        "30 November 1874, in Blenheim, Oxfordshire.",
        "Sir Winston Leonard Spencer [Churchill](#idx0) was Prime Minister "
        "from 1940 to 1945, and again from 1951 to 1955. [Churchill](#idx1) "
        "was born on 30 November 1874, in Blenheim, Oxfordshire.",
        entries,
        None,
    )

    test_case = "Prefix wildcards (^*^-; just entry's own heading)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="Prime Minister", parent=root)]
    entries.append(
        TextIndexEntry(
            label="Churchill, Sir Winston Leonard Spencer",
            parent=entries[-1],
        )
    )
    entries[-1].add_reference(0)
    entries.append(
        TextIndexEntry(
            label="Churchill, Sir Winston Leonard Spencer",
            parent=root,
        )
    )
    entries[-1].add_reference(1)
    yield (
        test_case,
        "Sir Winston Leonard Spencer "
        'Churchill{^"Prime Minister">"*, Sir Winston Leonard Spencer"} was '
        "Prime Minister from 1940 to 1945, and again from 1951 to 1955. "
        "Churchill{^*^-} was born on 30 November 1874, in Blenheim, "
        "Oxfordshire.",
        "Sir Winston Leonard Spencer [Churchill](#idx0) was Prime Minister "
        "from 1940 to 1945, and again from 1951 to 1955. [Churchill](#idx1) "
        "was born on 30 November 1874, in Blenheim, Oxfordshire.",
        entries,
        None,
    )

    test_case = "Sort keys"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="Greek letters", parent=root)]
    entries.append(TextIndexEntry(label="gamma", parent=entries[0]))
    entries[-1].add_reference(0)
    entries[-1].sort_key = "y"
    entries.append(TextIndexEntry(label="sigma", parent=entries[0]))
    entries[-1].add_reference(1)
    yield (
        test_case,
        'The Greek lowercase letter gamma{^"Greek letters"> ~y} looks like a '
        '"y", sigma{^"Greek letters">} does not.',
        'The Greek lowercase letter [gamma](#idx0) looks like a "y", '
        "[sigma](#idx1) does not.",
        entries,
        None,
    )

    test_case = "Sort keys (Index Letter Heading)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="gamma", parent=root)]
    entries[-1].add_reference(0)
    entries[-1].sort_key = "y"
    yield (
        test_case,
        'The Greek lowercase letter gamma{^ ~y} looks like a "y".',
        'The Greek lowercase letter [gamma](#idx0) looks like a "y".',
        entries,
        None,
    )

    test_case = "Closing marks for continuing locators"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="something", parent=root)]
    entries[-1].add_reference(0)
    entries[-1].update_latest_reference_end(1)
    yield (
        test_case,
        "The opening mark for something{^} ...\n"
        + "(lots of content goes here) ...\n" * int((297 / 25.4 * 72 // 10) + 1)
        + "and the closing mark for something{^/}.",
        "The opening mark for [something](#idx0) ...\n"
        + "(lots of content goes here) ...\n" * int((297 / 25.4 * 72 // 10) + 1)
        + "and the closing mark for [something](#idx1).",
        entries,
        None,
    )

    test_case = "Locator emphasis (first)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="combo", parent=root)]
    entries[-1].add_reference(0)
    yield (
        test_case,
        "With regard to computer keyboard firmware, a __combo__{^*} is a "
        "combination of simultaneously-pressed keys which perform a single "
        "action (such as pressing O+P to generate Backspace).",
        "With regard to computer keyboard firmware, a __[combo](#idx0)__ is a "
        "combination of simultaneously-pressed keys which perform a single "
        "action (such as pressing O+P to generate Backspace).",
        entries,
        None,
    )

    test_case = "Locator emphasis"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="combo", parent=root)]
    entries[-1].add_reference(0, locator_emphasis=True)
    yield (
        test_case,
        "With regard to computer keyboard firmware, a __combo__{^*!} is a "
        "combination of simultaneously-pressed keys which perform a single "
        "action (such as pressing O+P to generate Backspace).",
        "With regard to computer keyboard firmware, a __[combo](#idx0)__ is a "
        "combination of simultaneously-pressed keys which perform a single "
        "action (such as pressing O+P to generate Backspace).",
        entries,
        None,
    )

    test_case = "Locator suffixes"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="later works", parent=root)]
    entries[-1].add_reference(0, start_suffix="n.1")
    yield (
        test_case,
        "He would go on to discuss this in more detail in his "
        "[later works]{^[n.1]}.",
        "He would go on to discuss this in more detail in his "
        "[later works](#idx0).",
        entries,
        None,
    )

    test_case = "Locator suffixes (squared brackets)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="later works", parent=root)]
    entries[-1].add_reference(0, start_suffix="[n.1]")
    yield (
        test_case,
        "He would go on to discuss this in more detail in his "
        '[later works]{^["[n.1]"]}.',
        "He would go on to discuss this in more detail in his "
        "[later works](#idx0).",
        entries,
        None,
    )

    test_case = "Locator end suffixes"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="something", parent=root)]
    entries[-1].add_reference(0, start_suffix="n.1")
    entries[-1].update_latest_reference_end(1, end_suffix="n.2")
    yield (
        test_case,
        "The opening mark for something{^[n.1]} ...\n"
        + "(lots of content goes here) ...\n" * int((297 / 25.4 * 72 // 10) + 1)
        + "and the closing mark for something{^[n.2]/}.",
        "The opening mark for [something](#idx0) ...\n"
        + "(lots of content goes here) ...\n" * int((297 / 25.4 * 72 // 10) + 1)
        + "and the closing mark for [something](#idx1).",
        entries,
        None,
    )

    test_case = "Cross-references (see-type)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="destructive operation", parent=root)]
    entries[-1].add_cross_reference(
        0, CrossReferenceType.SEE, ["safety", "of functions"]
    )
    entries.append(TextIndexEntry(label="safety", parent=root))
    entries.append(TextIndexEntry(label="of functions", parent=entries[-1]))
    entries[-1].add_reference(1)
    yield (
        test_case,
        "This function can be [dangerous]"
        '{^"destructive operation"|safety>"of functions"}.'
        'This is the target of the [see-reference]{^safety>"of functions"}.',
        "This function can be [dangerous](#idx0)."
        "This is the target of the [see-reference](#idx1).",
        entries,
        None,
    )

    test_case = "Cross-references (also-type)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="risk", parent=root)]
    entries[-1].add_cross_reference(0, CrossReferenceType.SEE, ["ergonomics"])
    entries[-1].add_cross_reference(0, CrossReferenceType.ALSO, ["safety"])
    entries.append(TextIndexEntry(label="ergonomics", parent=root))
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="safety", parent=root))
    entries[-1].add_reference(2)
    yield (
        test_case,
        "Even typing on a keyboard can be surprisingly "
        'risky{^"risk"|ergonomics;+safety}.'
        "This is the target of the [see-reference]{^ergonomics} and "
        "[also-reference]{^safety}.",
        "Even typing on a keyboard can be surprisingly [risky](#idx0)."
        "This is the target of the [see-reference](#idx1) and "
        "[also-reference](#idx2).",
        entries,
        None,
    )

    test_case = "Inbound cross-references (see-type)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="inbound operation", parent=root)]
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="safety", parent=root))
    entries.append(TextIndexEntry(label="of types", parent=entries[-1]))
    entries[-1].add_cross_reference(
        0, CrossReferenceType.SEE, ["inbound operation"]
    )
    yield (
        test_case,
        'This function can be [cool]{^"inbound operation"|@safety>"of types"}.',
        "This function can be [cool](#idx0).",
        entries,
        None,
    )

    test_case = "Inbound cross-references (also-type)"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="risk", parent=root)]
    entries[-1].add_cross_reference(0, CrossReferenceType.SEE, ["ergonomics"])
    entries.append(TextIndexEntry(label="ergonomics", parent=root))
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="safety", parent=root))
    entries[-1].add_cross_reference(0, CrossReferenceType.ALSO, ["risk"])
    yield (
        test_case,
        "Even typing on a keyboard can be surprisingly "
        'risky{^"risk"|ergonomics;@+safety}.'
        "This is the target of the [see-reference]{^ergonomics}.",
        "Even typing on a keyboard can be surprisingly [risky](#idx0)."
        "This is the target of the [see-reference](#idx1).",
        entries,
        None,
    )

    test_case = "Defining and using aliases"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="Apple (company)", parent=root)]
    entries.append(TextIndexEntry(label="OS platforms", parent=entries[-1]))
    entries[-1].add_reference(0)
    entries.append(TextIndexEntry(label="iPhone", parent=root))
    entries[-1].add_reference(1)
    entries[-1].add_cross_reference(
        1,
        CrossReferenceType.ALSO,
        ["Apple (company)", "OS platforms"],
    )
    yield (
        test_case,
        "The various "
        '[operating systems]{^"Apple (company)">"OS platforms"#apple} on Apple '
        "devices share a common heritage in what was Mac OS X. "
        'The majority of Apple devices are iPhones{^"iPhone"|+#apple}, by a '
        "large margin.",
        "The various [operating systems](#idx0) on Apple devices share a "
        "common heritage in what was Mac OS X. "
        "The majority of Apple devices are [iPhones](#idx1), by a large "
        "margin.",
        entries,
        None,
    )

    test_case = "Unreferenced aliases"
    root = TextIndexEntry(label=None)
    entries = [
        TextIndexEntry(
            label="indeterminacy principle (Heisenberg, Werner Karl)",
            parent=root,
        )
    ]
    entries.append(TextIndexEntry(label="compensator", parent=root))
    entries[-1].add_cross_reference(
        0,
        CrossReferenceType.SEE,
        ["indeterminacy principle (Heisenberg, Werner Karl)"],
    )
    entries[0].add_reference(1)
    yield (
        test_case,
        '{^"indeterminacy principle (Heisenberg, Werner Karl)"##q-uncert}'
        "A key component of the Enterprise's transporter system is the "
        "Heisenberg compensator{^|#q-uncert}. This is the target{^#q-uncert}.",
        "A key component of the Enterprise's transporter system is the "
        "Heisenberg [compensator](#idx0). This is the [target](#idx1).",
        entries,
        None,
    )

    test_case = "Comprehensive example"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="foo", parent=root)]
    entries.append(TextIndexEntry(label="example text", parent=entries[-1]))
    entries[-1].add_cross_reference(0, CrossReferenceType.SEE, ["bar"])
    entries[-1].add_cross_reference(0, CrossReferenceType.ALSO, ["baz", "fiz"])
    entries[-1].sort_key = "z"
    entries.append(TextIndexEntry(label="bar", parent=root))
    entries[-1].add_reference(2)
    entries.append(TextIndexEntry(label="foo", parent=entries[-1]))
    entries.append(TextIndexEntry(label="example text", parent=entries[-1]))
    entries[-1].add_reference(1)
    entries.append(TextIndexEntry(label="baz", parent=root))
    entries.append(TextIndexEntry(label="fiz", parent=entries[-1]))
    entries[-1].add_reference(3)
    yield (
        test_case,
        '__example__{^foo>"* text"#demo |bar;+baz>fiz [whiz] ~z !}, '
        "__example-alias__{^bar>#demo}, __example-see__{^bar}, "
        "__example-also__{^baz>fiz}.",
        "__[example](#idx0)__, __[example-alias](#idx1)__, "
        "__[example-see](#idx2)__, __[example-also](#idx3)__.",
        entries,
        "Ignoring suffix/locator emphasis in cross reference: "
        "'__example__{^foo>\"* text\"#demo |bar;+baz>fiz [whiz] ~z !}'",
    )

    test_case = "Disabling and re-enabling TextIndex processing"
    root = TextIndexEntry(label=None)
    entries = [TextIndexEntry(label="bar", parent=root)]
    entries[-1].add_reference(0)
    yield (
        test_case,
        "{^-}This index mark won't be processed: foo{^}{^+}. "
        "This index mark will be processed: bar{^}.",
        "This index mark won't be processed: foo{^}. "
        "This index mark will be processed: [bar](#idx0).",
        entries,
        None,
    )


@pytest.fixture(autouse=True)
def reset_entry_next_id() -> None:
    TextIndexEntry._next_id = 0
    return

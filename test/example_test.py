import hashlib
import pathlib
import subprocess
import sys

import pytest

from test.conftest import DATA


@pytest.mark.parametrize(
    "example",
    [pathlib.Path(__file__).parents[1] / "example" / "textindex_figures.py"],
)
def test_example(example: pathlib.Path, tmp_path: pathlib.Path) -> None:
    result = subprocess.run(
        [sys.executable, "-u", example],
        cwd=tmp_path,
    )
    assert result.returncode == 0

    filename = example.with_suffix(".pdf").name
    actual_pdf_path = tmp_path / filename
    assert actual_pdf_path.exists()

    expected_pdf_path = DATA / filename

    actual_hash = hashlib.md5(actual_pdf_path.read_bytes()).hexdigest()
    expected_hash = hashlib.md5(expected_pdf_path.read_bytes()).hexdigest()

    assert actual_hash == expected_hash, f"{actual_hash} != {expected_hash}"

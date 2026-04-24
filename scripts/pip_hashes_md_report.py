"""Calculate hashes of pip-files (in directory 'dist')."""

# ruff: noqa: D103

import hashlib
import os
import pathlib
from typing import Final

CHUNK_SIZE: int = 1024 * 1024
FAVORITE_HASH: str = "sha256"

DIST: pathlib.Path = (pathlib.Path(__file__).parent / ".." / "dist").resolve()
MD_SPECIALS: Final[str] = r"\`*_{}[]()#+-.!|>"


def hash_of_file(path: os.PathLike[str], algorithm: str) -> str:
    hash = hashlib.new(algorithm)
    with pathlib.Path(path).open("rb") as archive:
        chunk = archive.read(CHUNK_SIZE)
        while chunk:
            hash.update(chunk)
            chunk = archive.read(CHUNK_SIZE)
    return hash.hexdigest()


def md_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch in MD_SPECIALS:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def main() -> None:
    out = ["# PyPI Dist Hashes  ", ""]
    for file in DIST.iterdir():
        if file.name == ".gitignore":
            continue
        hash = md_escape(hash_of_file(file, FAVORITE_HASH))
        filename = md_escape(file.relative_to(DIST).as_posix())
        out.append(f"- {filename:s}: {hash:s}  ")
    print("\n".join(out))


if __name__ == "__main__":
    main()

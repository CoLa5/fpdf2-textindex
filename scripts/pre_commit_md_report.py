"""Pre-commit Markdown Report."""

# ruff: noqa: D102,D103

import argparse
from collections.abc import Iterator
import re
import sys


def iter_input() -> Iterator[str]:
    yield from sys.stdin


class ReportBuilder:
    """Report Builder."""

    ANSI_RE: re.Pattern = re.compile(r"\x1b\[[0-9;]*m")  # ANSI color codes
    HEADER: tuple[str, ...] = (
        "# pre-commit Report",
        "",
        "| Hook | Status | Comments |",
        "|------|--------|----------|",
    )

    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []
        self.current = None
        self.stopped = False

    @classmethod
    def clean(cls, line: str) -> str:
        return cls.ANSI_RE.sub("", line).rstrip()

    @staticmethod
    def is_hook_line(line: str) -> bool:
        return "..." in line and line.strip().endswith(
            ("Passed", "Failed", "Skipped")
        )

    @staticmethod
    def is_stop_line(line: str) -> bool:
        return "pre-commit hook(s) made changes" in line

    def feed(self, raw: str) -> str:
        if self.stopped:
            return raw

        line = self.clean(raw)
        if not line:
            return raw

        if self.is_stop_line(line):
            self.finalize()
            self.stopped = True
            return raw

        if self.is_hook_line(line):
            if self.current:
                self.rows.append(self.current)

            parts = line.split(".")
            hook = parts[0].strip()
            status = parts[-1].strip()
            if status.startswith("(no files to check)"):
                status = status[len("(no files to check)") :]
            self.current = {
                "hook": hook.strip(),
                "status": status.strip(),
                "comments": [],
            }
        elif self.current and not line.startswith("- hook id"):
            self.current["comments"].append(line)
        return raw

    def finalize(self) -> None:
        if isinstance(self.current, str):
            self.rows.append(self.current)
            self.current = None

    def to_markdown_table(self) -> str:
        if not self.stopped:
            self.finalize()

        if not self.rows:
            return ""

        content = []
        for r in self.rows:
            comments = "<br>".join(r["comments"]) if r["comments"] else "-"
            content.append(
                f"| {r['hook']:s} | {r['status']:s} | {comments:s} |"
            )

        if self.stopped:
            content.extend(["", "**pre-commit hook(s) require changes**"])
        return "\n".join([*self.HEADER, *content])

    def write(self, report: str) -> None:
        try:
            fmt, target = report.split(":", 1)
        except ValueError as e:
            msg = (
                f"Invalid format {report!r:s}, use 'markdown:file.md' or "
                f"'markdown-append:file.md'"
            )
            raise ValueError(msg) from e

        if fmt not in ("markdown", "markdown-append"):
            msg = f"unsupported format: {fmt!r:s}"
            raise ValueError(msg)

        if fmt == "markdown-append":
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n" + self.to_markdown_table() + "\n")
        else:
            with open(target, "w", encoding="utf-8") as f:
                f.write(self.to_markdown_table() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-r",
        "--report",
        help="Report markdown path ('markdown:file', 'markdown-append:file')",
        required=True,
    )
    args = parser.parse_args()

    builder = ReportBuilder()
    for line in iter_input():
        sys.stdout.write(builder.feed(line))
        sys.stdout.flush()
    builder.write(args.report)


if __name__ == "__main__":
    main()

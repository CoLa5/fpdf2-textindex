"""Pre-commit Markdown Report."""

# ruff: noqa: D102,D103

import argparse
from collections.abc import Iterator
import re
import sys
from typing import Final


def iter_input() -> Iterator[str]:
    yield from sys.stdin


class ReportBuilder:
    """Report Builder."""

    ANSI_RE: re.Pattern = re.compile(r"\x1b\[[0-9;]*m")  # ANSI color codes
    MD_SPECIALS: Final[str] = r"\`*_{}[]()#+-.!|>"

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

    @classmethod
    def md_escape(cls, text: str) -> str:
        out = []
        for ch in text:
            if ch == "\\":
                out.append("\\\\")
            elif ch in cls.MD_SPECIALS:
                out.append("\\" + ch)
            else:
                out.append(ch)
        return "".join(out)

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
        elif self.current and line.startswith("- "):
            self.current["comments"].append(line)
        return raw

    def finalize(self) -> None:
        if isinstance(self.current, dict):
            self.rows.append(self.current)
            self.current = None

    def to_markdown_table(self) -> str:
        if not self.stopped:
            self.finalize()

        if not self.rows:
            return ""

        # Escape row values and calculate column width
        c_len = {"hook": 4, "status": 6, "comments": 8}
        rows = []
        for r in self.rows:
            hook = self.md_escape(r["hook"])
            c_len["hook"] = max(c_len["hook"], len(hook))

            status = self.md_escape(r["status"])
            c_len["status"] = max(c_len["status"], len(status))

            comments = (
                "<br>".join("- " + self.md_escape(c[2:]) for c in r["comments"])
                if r["comments"]
                else "-"
            )
            c_len["comments"] = max(c_len["comments"], len(comments))
            rows.append({"hook": hook, "status": status, "comments": comments})

        # Create content
        content = []
        content.append(
            "|".join(
                [
                    "",
                    f" {'Hook':<{c_len['hook']:d}s} ",
                    f" {'Status':>{c_len['status']:d}s} ",
                    f" {'Comments':<{c_len['comments']:d}s} ",
                    "",
                ]
            )
        )
        content.append(
            "|".join(
                [
                    "",
                    f" {'':-<{c_len['hook']:d}s} ",
                    f" {'':->{c_len['status'] - 1:d}s}: ",
                    f" {'':-<{c_len['comments']:d}s} ",
                    "",
                ]
            )
        )
        for r in rows:
            content.append(
                "|".join(
                    [
                        "",
                        f" {r['hook']:<{c_len['hook']:d}s} ",
                        f" {r['status']:>{c_len['status']:d}s} ",
                        f" {r['comments']:<{c_len['comments']:d}s} ",
                        "",
                    ]
                )
            )
        content.append("")
        if self.stopped:
            content.extend(["**pre-commit hook(s) require(s) changes**", ""])
        return "\n".join(content)

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

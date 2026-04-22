#!/usr/bin/env python3
"""Make docs."""

import itertools
import pathlib
import shutil
import textwrap
from typing import Final

import pdoc.render

import fpdf2_textindex

HERE: Final[pathlib.Path] = pathlib.Path(__file__).parent
DOC_URL: Final[str] = "https://cola5.github.io/fpdf2-textindex"
GIT_URL: Final[str] = "https://github.com/CoLa5/fpdf2-textindex"


def write_sitemap(path: pathlib.Path) -> None:  # noqa: D103
    with (path / "sitemap.xml").open("w", newline="\n") as f:
        header = """
            <?xml version="1.0" encoding="utf-8"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">
            """
        f.write(textwrap.dedent(header).strip())
        for file in path.glob("**/*.html"):
            if file.name.startswith("_"):
                continue
            filename = (
                file.relative_to(path).as_posix().replace("index.html", "")
            )
            f.write(f"""\n<url><loc>{DOC_URL:s}/{filename:s}</loc></url>""")
        f.write("""\n</urlset>""")


if __name__ == "__main__":
    pdoc.render.configure(
        docformat="google",
        edit_url_map={
            "fpdf2_textindex": f"{GIT_URL:s}/blob/main/fpdf2_textindex/",
        },
        favicon="assets/favicon.svg",
        footer_text=(
            f'<a href="{GIT_URL:s}/releases/tag/'
            f'v{fpdf2_textindex.__version__:s}">'
            f"fpdf2_textindex <b>v{fpdf2_textindex.__version__:s}</b>"
            f"</a>"
        ),
        logo="assets/logo.svg",
        logo_link=DOC_URL,
        search=True,
        template_directory=HERE / "pdoc_template",
    )
    output = HERE / ".." / "public"
    output.mkdir(exist_ok=True)
    pdoc.pdoc(
        HERE / ".." / "fpdf2_textindex",
        output_directory=output,
    )
    # Remove unnecessary forwarding index
    (output / "fpdf2_textindex.html").replace(output / "index.html")

    write_sitemap(output)

    # Copy icons
    (output / "assets").mkdir(exist_ok=True)
    for name, suffix in itertools.product(
        ("favicon", "logo"),
        (".png", ".svg"),
    ):
        filename = name + suffix
        shutil.copy2(
            HERE / "icons" / filename,
            output / "assets" / filename,
        )
    # Copy robots.txt
    shutil.copy2(HERE / "robots.txt", output / "robots.txt")

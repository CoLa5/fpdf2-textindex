"""Example."""

# ruff: noqa: E501

import datetime as dt
import logging
import pathlib

import fpdf

from fpdf2_textindex import FPDF
from fpdf2_textindex import TextIndexRenderer

EXAMPLES: list[tuple[str, str]] = [
    (
        "Empty entry",
        "{^}",
    ),
    (
        "Marking entries",
        "Most mechanical keyboard firmware{^} supports the use of [key combinations]{^}.",
    ),
    (
        "Heading overrides",
        'This is a standalone mark: {^"foo bar"}and this one has an overridden [heading]{^"foo baz"}.',
    ),
    (
        "Nested headings",
        'This is a standalone nested mark: {^"foo bar">baz}and this one will create an identical entry: [baz]{^"foo bar">}.',
    ),
    (
        "Emphasised and expanded headings",
        'This entry will be **bold**{^}, __italics__{^}, --underline--{^},  ~~strikethrough~~{^} or **__bolditalics__**{^} in the index. This expanded entry won\'t be __emphasised__{^"* (nope)"}.',
    ),
    (
        "Emphasis-stripping with wildcards",
        "This entry won't be **bold**{^*}, __italics__{^*}, --underline--{^*} or ~~strikethrough~~{^*}.",
    ),
    (
        "Prefix wildcards",
        'Sir Winston Leonard Spencer Churchill{^"*, Sir Winston Leonard Spencer"} was Prime Minister from 1940 to 1945, and again from 1951 to 1955. Churchill{^*^} was born on 30 November 1874, in Blenheim, Oxfordshire.',
    ),
    (
        "Sort keys",
        'The Greek lowercase letter gamma{^"Greek letters"> ~y} looks like a "y", sigma{^"Greek letters">} does not.',
    ),
    (
        "Closing marks for continuing locators",
        "The opening mark for something{^}\n"
        + "... (lots of content goes here) ...\n"
        * (int(180 / 25.4 * 72 / 12) - 2)
        + "and the closing mark for something{^/}.",
    ),
    (
        "Locator emphasis",
        "With regard to computer keyboard firmware, a __combo__{^*!} is a combination of simultaneously-pressed keys which perform a single action (such as pressing O+P to generate Backspace).",
    ),
    (
        "Locator suffixes",
        "He would go on to discuss this in more detail in his [later works]{^[n.1]}.",
    ),
    (
        "Locator end suffix",
        "The opening mark for something{^[n.1]}\n"
        + "... (lots of content goes here) ...\n"
        * (int(180 / 25.4 * 72 / 12) - 2)
        + "and the closing mark for something{^[n.2]/}.",
    ),
    (
        "Cross-references (see-type)",
        'This function can be [dangerous]{^"destructive operation"|safety>"of functions"}.',
    ),
    (
        "Cross-references (see-type) target",
        'This is the target of the [see-reference]{^safety>"of functions"}.',
    ),
    (
        "Cross-references (also-type)",
        'Even typing on a keyboard can be surprisingly risky{^"risk"|ergonomics;+safety}.',
    ),
    (
        "Cross-references (also-type) target",
        "This is the target of the [see-reference]{^ergonomics} and [also-reference]{^safety}.",
    ),
    (
        "Inbound cross-references (see-type)",
        'This function can be [cool]{^"inbound operation"|@safety>"of types"}.',
    ),
    (
        "Inbound cross-references (also-type)",
        'Even typing on a keyboard can be surprisingly risky{^"risk"|ergonomics;@+safety}.',
    ),
    (
        "Defining and using aliases",
        'The various [operating systems]{^"Apple (company)">"OS platforms"#apple} '
        "on Apple devices share a common heritage in what was Mac OS X. "
        'The majority of Apple devices are iPhones{^"iPhone"|+#apple}, by a large margin.',
    ),
    (
        "Unreferenced aliases",
        '{^"indeterminacy principle (Heisenberg, Werner Karl)"##q-uncert}'
        "A key component of the Enterprise's transporter system is the "
        "Heisenberg compensator{^|#q-uncert}",
    ),
    (
        "Unreferenced aliases target",
        "Key component{^#q-uncert}",
    ),
    (
        "Comprehensive example",
        '__example__{^foo>"* text"#demo |bar;+baz>fiz [whiz] ~z !}',
    ),
    (
        "Comprehensive example target",
        "__example see__{^bar} __example also__{^baz>fiz}",
    ),
    (
        "Disabling and re-enabling TextIndex processing",
        "{^-} This index mark won't be processed: foo{^} {^+}",
    ),
    (
        "Concordance example",
        "single-tap iPad or double-tapped ipad lead to simultaneous layer chords{^chord}",
    ),
]
HERE: pathlib.Path = pathlib.Path(__file__).parent.resolve()
LOGGER: logging.Logger = logging.getLogger(__name__)


def main() -> None:
    """Main function."""
    logging.basicConfig(level=logging.INFO)

    doc = FPDF(format="A5")
    doc.CONCORDANCE_FILE = (HERE / "concordance.tsv").as_posix()
    doc.MARKDOWN_LINK_COLOR = "#0000FF"
    doc.MARKDOWN_LINK_UNDERLINE = False
    doc.set_font("Helvetica", size=12)

    # Insert Text Index (including heading)
    doc.add_page(label_style="R", label_start=1)
    with doc.use_text_style(
        fpdf.TextStyle(
            font_style="B",
            color="#FF0000",
            l_margin=doc.l_margin + 0.2 * doc.font_size,
            t_margin=0.5 * doc.font_size,
        )
    ):
        doc.multi_cell(
            w=0,
            h=1.2 * doc.font_size,
            text="Text Index",
            align="L",
            new_x="left",
            new_y="next",
        )

    index = TextIndexRenderer(
        line_spacing=1.2,
        text_styles=[
            fpdf.TextStyle(
                font_style="B",
                color="#FF0000",
                l_margin=doc.l_margin + 0.2 * doc.font_size,
                t_margin=0.5 * doc.font_size,
            ),
            fpdf.TextStyle(
                l_margin=doc.l_margin,
            ),
        ],
        max_outline_level=0,
        outline_level=0,
        show_header=True,
        sort_emph_first=True,
    )
    doc.insert_index_placeholder(
        index.render_text_index,
        allow_extra_pages=True,
    )

    # Insert example pages
    doc.set_page_label(label_style="D", label_start=1)
    for i, (cmt, example) in enumerate(EXAMPLES):
        if i > 0:
            doc.add_page()
        doc.multi_cell(
            w=0,
            text=cmt,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )
        doc.multi_cell(
            w=0,
            text=example,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )
        doc.multi_cell(
            w=0,
            text=example,
            markdown=True,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )

    # Print with fixed creation date
    doc.creation_date = dt.datetime(1969, 12, 31, 19, 00, 00).replace(
        tzinfo=dt.timezone.utc
    )
    doc.output("textindex_figures.pdf")


if __name__ == "__main__":
    main()

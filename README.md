[![Pypi latest version](https://img.shields.io/pypi/v/fpdf2_textindex?pypiBaseUrl=https%3A%2F%2Ftest.pypi.org)](https://test.pypi.org/project/fpdf2_textindex#history)
[![Python Support](https://img.shields.io/pypi/pyversions/fpdf2_textindex?pypiBaseUrl=https%3A%2F%2Ftest.pypi.org)](https://test.pypi.org/project/fpdf2_textindex/)
[![Documentation](https://img.shields.io/badge/docs-github.io-blue)](https://cola5.github.io/fpdf2-textindex)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0)

[![CI](https://github.com/CoLa5/fpdf2-textindex/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/CoLa5/fpdf2-textindex/actions/workflows/ci.yml)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/CoLa5/fpdf2-textindex/blob/main/.pre-commit-config.yaml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/CoLa5/d548905d5994ebc1c3f15e8cfb9003e2/raw/covbadge.json)](https://cola5.github.io/fpdf2-textindex/coverage/)
[![GitHub last commit](https://img.shields.io/github/last-commit/CoLa5/fpdf2-textindex)](https://github.com/CoLa5/fpdf2-textindex/commits/main)

# fpdf2 Text Index

<img src="https://cola5.github.io/fpdf2-textindex/assets/logo.svg" title="fpdf2_textindex logo" width="25%"/>

Adds a **text index** to [fpdf2](https://github.com/py-pdf/fpdf2), based on the
documentation and source code of
[Math Gemmell's Text Index](https://mattgemmell.scot/textindex/):

```python3
from fpdf2_textindex import FPDF, TextIndexRenderer

pdf = FPDF()
pdf.add_page()
pdf.set_font('helvetica', size=12)
# Adding text index entry "example
pdf.cell(text="example{^}", markdown=True)
# Add the text index to a page
pdf.add_page()
pdf.insert_index_placeholder(TextIndexRenderer().render_text_index)
# Save as pdf
pdf.output("example.pdf")
```

## Adding a Text Index Entry

Use the [text index-syntax](https://mattgemmell.scot/textindex/) to define index
directives in a text:

> Most mechanical keyboard firmware{^} supports the use of [key
> combinations]{^}.

Print it in the PDF by enabling markdown in `fpdf2.FPDF.cell` or
`fpdf2.FPDF.multi_cell`:

```python3
pdf = FPDF()
pdf.add_page()
pdf.set_font('helvetica', size=12)
pdf.cell(
  text="Most mechanical keyboard firmware{^} supports the use of [key combinations]{^}.",
  markdown=True,
)
...
```

For a complete documentation of the supported text index directives, see the
[excellent documentation of Math Gemmell](https://mattgemmell.scot/textindex).

The only difference to this documentation is the adaption of the emphasis to the
[markdown style of fpdf2](https://py-pdf.github.io/fpdf2/TextStyling.html#markdowntrue).
So the text:

> This entry will be **\*\*emphasised\*\***{^} in the index.  
> This expanded entry will be **\*\*[not emphasised]{^"\* (nope)"}\*\*** in the
> index but here in the text.

will be printed in the PDF as:

> This entry will be **emphasised** in the index.  
> This expanded entry will be **not emphasised** in the index but here in the
> text.

Similarly, the marks for italics `__`, underline `--` and strikethrough `~~` are
supported.

## Inserting a Text Index

Use the adapted FPDF-class of this package that offers a
`fpdf2_textindex.FPDF.insert_index_placeholder`-method to define a placeholder
for the **text index**. A page break is triggered after inserting the text
index:

```python3
...
pdf.add_page()
pdf.insert_index_placeholder(render_index_function)
```

Parameters:

- `render_index_function`: Function called to render the text index, receiving
  two parameters: `pdf`, an adapted `FPDF` instance, and `entries`, a list of
  `fpdf2_textindex.TextIndexEntry`s. A reference implementation is supported
  through `fpdf2_textindex.TextIndexRenderer.render_text_index`.
- `pages`: The number of pages that the text index will span, including the
  current one. A page break occurs for each page specified.
- `allow_extra_pages`: If `True`, allows unlimited additional pages to be added
  to the text index as needed. These extra text index pages are initially
  created at the end of the document and then reordered when the final PDF is
  produced.

**Note**: Enabling `allow_extra_pages` may affect page numbering for headers or
footers. Since extra text index pages are added after the document content, they
might cause page numbers to appear out of sequence. To maintain consistent
numbering, use **Page Labels** to assign a specific numbering style to the index
pages. When using Page Labels, any extra text index pages will follow the
numbering style of the first text index page

## Example

An example can be created by
[`example/textindex_figures.py`](https://github.com/CoLa5/fpdf2-textindex/blob/main/example/textindex_figures.py#L130)
and produces
[textindex_figures.pdf](https://cola5.github.io/fpdf2-textindex/assets/textindex_figures.pdf)
with all the examples from
[Math Gemmell's website](https://mattgemmell.scot/textindex/).s

---

## Internals - Idea

For the curious reader:

This package adds a markdown parser to [fpdf2](https://github.com/py-pdf/fpdf2)
that intercepts markdown-styled strings to `fpdf2.FPDF.cell` or
`fpdf2.FPDF.multi_cell` and translates
[Math Gemmell's Text Index](https://mattgemmell.scot/textindex/)-directives into
markdown-links with an unset internal PDF link as destination, while the created
index entries are internally saved:

`"example{^}"`  
 **=**  
`"[example](#idx0)"`  
 **+**  
`TextIndexEntry(label="example", references=[Reference(start_id=0)])`

When creating the actual text index in the PDF, all unset internal PDF link
annotations that are related to the text index (identified by an unique id
schema) are collected and its page, x/y-position on the page added to the
entry's references:

`{"idx0": LinkLocation(page=3, x=20.0, y=40.0, ...), ...}`  
 **->**  
`TextIndexEntry.references[0].start_location = LinkLocation(page=3, x=20.0, y=40.0, ...)`

Finally, a `render_index_function` similar to the
[official TOC-implementation of fpdf2](https://py-pdf.github.io/fpdf2/DocumentOutlineAndTableOfContents.html#table-of-contents)
is used to render the index. The package supports a reference implementation,
but the user can implement its own version if necessary.

The reference `render_index_function` renders each index entry according to
[The Chicago Manual of Style - Indexes](https://www.chicagomanualofstyle.org/book/ed18/part3/ch15/toc.html).
The references (locators) of each entry are matched by its id to an unset link
annotation in the PDF and, thus, to a page number/label, which is used to print
the reference (locator) in the index:

`"example, 3"`

The unset link annotation in the text is pointed to this entry in the index and,
thus, is finally set.

In the reference implementation, inverted links are added as well: To create a
connection of the index entry to the text page, the printed page number will
point to the text page as well.  
So clicking on `"example"` on the text page will lead to corresponding entry in
the text index. Clicking on the reference (locator) in the text index, page
`"3"`, will return the reader to the text page. Cross-references are connected
in the same way but inside of the text index.

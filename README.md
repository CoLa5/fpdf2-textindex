# fpdf2 TextIndex

Adds a **text index** to [fpdf2](https://github.com/py-pdf/fpdf2), based on the
documentation and source code of
[Math Gemmell's TextIndex](https://mattgemmell.scot/textindex/).

## Inserting a Text Index

Use the `insert_index_placeholder`-method to define a placeholder for the **text
index**. A page break is triggered after inserting the text index.

Parameters:

- `render_index_function`: Function called to render the text index, receiving
  two parameters: `pdf`, an `FPDF` instance, and `entries`, a list of
  `TextIndexEntry`s.
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

## Idea

Add a markdown parser to [fpdf2](https://github.com/py-pdf/fpdf2) that
intercepts markdown-styled strings to `FPDF.cell(...)` or `FPDF.multi_cell(...)`
and translates [Math Gemmell's TextIndex](https://mattgemmell.scot/textindex/)-
directives into markdown-links with an unset internal PDF link as destination,
while the created index entries are internally saved:

`"firmware{^}"`  
**=**  
`"[firmware](#idx0)"`  
**+**  
`TextIndexEntry(label="firmware", references=[Reference(start_id=0)])`

When creating the index, a `render_index_function` like in the
[official TOC-implementation of fpdf2](https://py-pdf.github.io/fpdf2/DocumentOutlineAndTableOfContents.html#table-of-contents)
is used. The `render_index_function` collects all unset internal PDF link
annotations that are related to the text index (identified by an unique id
schema). The annotations are collected per page and have the x/y-position on the
page as attribute:

`{"idx0": LinkLocation(name="idx0", page=3, x=20.0, y=40.0), ...}`

The `render_index_function` renders each index entry according to
[The Chicago Manual of Style - Indexes](https://www.chicagomanualofstyle.org/book/ed18/part3/ch15/toc.html).
The references (locators) of each entry are matched by its id to an unset link
annotation in the PDF and, thus, to a page number/label, which is used to print
the reference (locator) in the index:

`"firmware, 3"`

The unset link annotation in the text is pointed to this entry in the index and,
thus, is finally set. To create a connection of the index entry to the text
page, the printed page number will point to the text page as well.  
So clicking on `"firmware"` on the text page will lead to corresponding index
entry. Clicking on the reference (locator), page `"3"`, in the text index will
return the reader to the text page.  
Cross-references are connected in the same way but inside of the text index.

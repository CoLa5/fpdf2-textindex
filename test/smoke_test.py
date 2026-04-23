"""Check that basic features work.

Catch cases where e.g. files are missing so the import doesn't work. It is
recommended to check that e.g. assets are included."""

from fpdf2_textindex import FPDF

pdf = FPDF()

print("Basic import does work")

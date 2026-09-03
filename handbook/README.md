# Project Handbook

`PROJECT_HANDBOOK.pdf` — 324 pages. The complete technical, learning and viva handbook for
this project, built entirely from the actual repository on this machine.

| File | What it is |
|---|---|
| `PROJECT_HANDBOOK.pdf` | the handbook (A4, plain text, table of contents, page numbers) |
| `PROJECT_HANDBOOK.md` | the editable source. **Edit this**, not the PDF |
| `build_handbook.py` | the Markdown-to-PDF builder (ReportLab) |

## Rebuilding after editing the Markdown

```
python3 -m venv .venv
.venv/bin/pip install reportlab
.venv/bin/python build_handbook.py PROJECT_HANDBOOK.md PROJECT_HANDBOOK.pdf
```

The builder uses the system fonts in `/System/Library/Fonts/Supplemental`
(Times New Roman, Arial, Courier New), so it runs on macOS as-is.

## Source syntax

`# PART n — Title || subtitle` a part divider page; `## Chapter n — Title` a chapter
(new page); `### x.y Title` a section; `#### Title` a subsection. Pipe tables, fenced
code blocks (` ```python ` and ` ```diagram `), `^^ caption` after a table or block,
`<<<PAGEBREAK>>>`, and labelled blocks:

```
:::simple | :::professor | :::remember | :::caution | :::truth | :::key   Optional title
body
:::
```

## Note

This folder contains documentation only. Nothing in it touches the project
implementation, and no project file was modified to produce it.

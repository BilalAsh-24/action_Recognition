#!/usr/bin/env python
"""Build PROJECT_HANDBOOK.pdf from the Markdown-subset source.

Usage:  python build_handbook.py <source.md> <out.pdf>

Supported source syntax
-----------------------
%%COVER ... %%END          cover-page fields (key: value)
# PART ...                 part divider page   (TOC level 0)
## Chapter N - ...         chapter, new page   (TOC level 1)
### x.y Section            section             (TOC level 2)
#### Subsection            subsection          (not in TOC)
paragraph text             **bold** *italic* `code`
- bullet / 1. numbered     lists (one level of nesting with two spaces)
| a | b |                  pipe table (row 2 = separator)
```lang ... ```            code block (lang 'diagram' -> framed monospace figure)
:::kind Title ... :::      callout box: simple | professor | remember | warning |
                           truth | q | key
---                        horizontal rule
<<<PAGEBREAK>>>            forced page break
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame,
                                KeepTogether, ListFlowable, ListItem, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Preformatted,
                                Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
SUP = "/System/Library/Fonts/Supplemental"
FONTS = {
    "Body":        f"{SUP}/Times New Roman.ttf",
    "Body-Bold":   f"{SUP}/Times New Roman Bold.ttf",
    "Body-Italic": f"{SUP}/Times New Roman Italic.ttf",
    "Body-BoldItalic": f"{SUP}/Times New Roman Bold Italic.ttf",
    "Head":        f"{SUP}/Arial.ttf",
    "Head-Bold":   f"{SUP}/Arial Bold.ttf",
    "Head-Italic": f"{SUP}/Arial Italic.ttf",
    "Mono":        f"{SUP}/Courier New.ttf",
    "Mono-Bold":   f"{SUP}/Courier New Bold.ttf",
}


def register_fonts():
    for name, path in FONTS.items():
        if not os.path.isfile(path):
            raise SystemExit(f"font missing: {path}")
        pdfmetrics.registerFont(TTFont(name, path))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                                  italic="Body-Italic", boldItalic="Body-BoldItalic")
    pdfmetrics.registerFontFamily("Head", normal="Head", bold="Head-Bold",
                                  italic="Head-Italic", boldItalic="Head-Bold")
    pdfmetrics.registerFontFamily("Mono", normal="Mono", bold="Mono-Bold",
                                  italic="Mono", boldItalic="Mono-Bold")


# characters that are not in the chosen fonts, mapped to safe equivalents
CHAR_MAP = {
    "\u2192": "->", "\u2190": "<-", "\u2191": "^", "\u2193": "v",
    "\u21d2": "=>", "\u2794": "->", "\u27f6": "->",
    "\u2713": "[ok]", "\u2714": "[ok]", "\u2717": "[x]", "\u2718": "[x]",
    "\u2705": "[ok]", "\u274c": "[x]", "\u26a0": "!",
    "\u2265": ">=", "\u2264": "<=", "\u2260": "!=", "\u2248": "~",
    "\u00d7": "x", "\u2212": "-", "\u221a": "sqrt", "\u2211": "sum",
    "\u0394": "delta", "\u03c3": "sigma", "\u03bc": "u", "\u03b8": "theta",
    "\u2033": '"', "\u2032": "'", "\u2022": "*", "\u25cf": "*", "\u25e6": "o",
    "\u2014": "\u2014", "\u2013": "\u2013",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00a0": " ", "\u2009": " ", "\u200a": " ", "\u202f": " ",
    "\u2502": "|", "\u2500": "-", "\u250c": "+", "\u2510": "+",
    "\u2514": "+", "\u2518": "+", "\u251c": "+", "\u2524": "+",
    "\u252c": "+", "\u2534": "+", "\u253c": "+",
    "\u2550": "=", "\u2551": "|",
}


def sanitize(s: str) -> str:
    for a, b in CHAR_MAP.items():
        s = s.replace(a, b)
    return s


# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
INK = colors.black
INK_SOFT = colors.black
ACCENT = colors.black
ACCENT_L = colors.white
RULE = colors.black
GREY_BG = colors.white
CODE_BG = colors.white
CODE_BR = colors.black

CALLOUTS = {
    "simple":    ("SIMPLE EXPLANATION",),
    "professor": ("PROFESSOR MAY ASK",),
    "remember":  ("REMEMBER THIS",),
    "warning":   ("CAUTION",),
    "truth":     ("EVIDENCE IN THE PROJECT",),
    "key":       ("KEY POINT",),
    "q":         ("QUESTION",),
}
ALIAS = {"caution": "warning", "evidence": "truth", "project": "truth",
         "note": "key", "answer": "q", "viva": "q", "trap": "warning"}

PAGE_W, PAGE_H = A4
M_L, M_R, M_T, M_B = 21 * mm, 17 * mm, 22 * mm, 20 * mm
CONTENT_W = PAGE_W - M_L - M_R

# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
S = {}


def build_styles():
    S["body"] = ParagraphStyle("body", fontName="Body", fontSize=10.2, leading=15.0,
                               textColor=INK, alignment=TA_JUSTIFY, spaceAfter=6.5)
    S["body_l"] = ParagraphStyle("body_l", parent=S["body"], alignment=TA_LEFT)
    S["lead"] = ParagraphStyle("lead", parent=S["body"], fontSize=11.0, leading=16.5,
                               textColor=INK_SOFT)
    S["part_no"] = ParagraphStyle("part_no", fontName="Body-Bold", fontSize=12,
                                  textColor=INK, alignment=TA_LEFT, spaceAfter=6,
                                  leading=16)
    S["part"] = ParagraphStyle("part", fontName="Body-Bold", fontSize=22, leading=27,
                               textColor=INK, alignment=TA_LEFT, spaceAfter=10)
    S["part_sub"] = ParagraphStyle("part_sub", fontName="Body-Italic", fontSize=11.5,
                                   leading=17, textColor=INK_SOFT, alignment=TA_LEFT)
    S["h1"] = ParagraphStyle("h1", fontName="Body-Bold", fontSize=15.5, leading=20,
                             textColor=INK, spaceBefore=0, spaceAfter=9)
    S["h2"] = ParagraphStyle("h2", fontName="Body-Bold", fontSize=12, leading=16,
                             textColor=INK, spaceBefore=13, spaceAfter=5)
    S["h3"] = ParagraphStyle("h3", fontName="Body-Bold", fontSize=10.4, leading=14,
                             textColor=INK, spaceBefore=9, spaceAfter=3)
    S["li"] = ParagraphStyle("li", parent=S["body"], alignment=TA_LEFT, spaceAfter=3.2)
    S["code"] = ParagraphStyle("code", fontName="Mono", fontSize=7.9, leading=10.4,
                               textColor=INK)
    S["diag"] = ParagraphStyle("diag", fontName="Mono", fontSize=7.4, leading=10.0,
                               textColor=INK)
    S["cap"] = ParagraphStyle("cap", fontName="Body-Italic", fontSize=8.2, leading=11,
                              textColor=INK_SOFT, spaceBefore=2, spaceAfter=8)
    S["th"] = ParagraphStyle("th", fontName="Body-Bold", fontSize=8.6, leading=11.2,
                             textColor=INK)
    S["td"] = ParagraphStyle("td", fontName="Body", fontSize=8.5, leading=11.4,
                             textColor=INK)
    S["td_m"] = ParagraphStyle("td_m", fontName="Body", fontSize=8.5, leading=11.4,
                               textColor=INK)
    S["co_t"] = ParagraphStyle("co_t", fontName="Body-Bold", fontSize=9.4, leading=13,
                               textColor=INK, spaceAfter=2)
    S["co_b"] = ParagraphStyle("co_b", parent=S["body"], fontSize=9.7, leading=14,
                               spaceAfter=4, alignment=TA_LEFT)
    S["toc0"] = ParagraphStyle("toc0", fontName="Body-Bold", fontSize=10, leading=16,
                               textColor=INK, spaceBefore=7)
    S["toc1"] = ParagraphStyle("toc1", fontName="Body", fontSize=9.4, leading=13.6,
                               leftIndent=10, textColor=INK)
    S["toc2"] = ParagraphStyle("toc2", fontName="Body", fontSize=8.6, leading=12.2,
                               leftIndent=24, textColor=INK_SOFT)
    # cover
    S["cv_kick"] = ParagraphStyle("cv_kick", fontName="Body", fontSize=10.5,
                                  textColor=INK, alignment=TA_CENTER, leading=14)
    S["cv_title"] = ParagraphStyle("cv_title", fontName="Body-Bold", fontSize=22,
                                   textColor=INK, alignment=TA_CENTER, leading=35)
    S["cv_sub"] = ParagraphStyle("cv_sub", fontName="Body-Italic", fontSize=13.5,
                                 textColor=INK_SOFT, alignment=TA_CENTER, leading=19)
    S["cv_meta"] = ParagraphStyle("cv_meta", fontName="Body", fontSize=10,
                                  textColor=INK_SOFT, alignment=TA_CENTER, leading=15)
    S["cv_small"] = ParagraphStyle("cv_small", fontName="Body", fontSize=9,
                                   textColor=INK_SOFT, alignment=TA_CENTER, leading=12)


# --------------------------------------------------------------------------- #
# Inline markup
# --------------------------------------------------------------------------- #
def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def inline(text: str) -> str:
    """Markdown inline -> reportlab mini-HTML."""
    text = sanitize(text)
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "`":
            j = text.find("`", i + 1)
            if j > 0:
                out.append('<font face="Mono" size="8.8">'
                           + esc(text[i + 1:j]) + "</font>")
                i = j + 1
                continue
        if text.startswith("**", i):
            j = text.find("**", i + 2)
            if j > 0:
                out.append("<b>" + inline(text[i + 2:j]) + "</b>")
                i = j + 2
                continue
        if c == "*" and not text.startswith("**", i):
            j = text.find("*", i + 1)
            if j > 0 and j > i + 1:
                out.append("<i>" + inline(text[i + 1:j]) + "</i>")
                i = j + 1
                continue
        out.append(esc(c))
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# Custom flowables
# --------------------------------------------------------------------------- #
class Rule(Flowable):
    def __init__(self, width, thickness=0.7, color=RULE, space=4, center=False):
        Flowable.__init__(self)
        self.width, self.thickness, self.color, self.space = width, thickness, color, space
        self.center = center
        self._x = 0

    def wrap(self, aw, ah):
        self._x = (aw - self.width) / 2.0 if self.center else 0
        return (aw if self.center else self.width, self.thickness + self.space * 2)

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(self._x, self.space, self._x + self.width, self.space)


class Bookmark(Flowable):
    """Zero-height marker used for running headers and page-number origin."""

    def __init__(self, kind, text=""):
        Flowable.__init__(self)
        self.kind, self.text = kind, text
        self.width = self.height = 0

    def wrap(self, aw, ah):
        return (0, 0)

    def draw(self):
        pass


class HeadingFlowable(Paragraph):
    """Paragraph that also registers a TOC entry and a running-header value."""

    def __init__(self, text, style, level, header, toc_text=None):
        Paragraph.__init__(self, text, style)
        self.toc_level = level
        self.header_text = header
        self.toc_text = toc_text if toc_text is not None else text


def make_callout(kind, title, flows, width):
    """A plain labelled block: bold label line, then the body, indented.

    No fill, no colour, no rules. The label carries the meaning.
    """
    label = CALLOUTS[kind][0]
    head = label if not title else f"{label}: {sanitize(title)}"
    rows = [[Paragraph(inline(head), S["co_t"])]]
    for f in flows:
        rows.append([f])
    t = Table(rows, colWidths=[width - 16], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (0, 0), 3),
        ("BOTTOMPADDING", (0, -1), (0, -1), 3),
    ]))
    t.splitByRow = 1
    return t


class CodeBox(Flowable):
    """Framed monospace block; splits across pages."""

    def __init__(self, lines, width, style, caption=None, tint=CODE_BG, border=CODE_BR):
        Flowable.__init__(self)
        self.lines = lines
        self.width = width
        self.style = style
        self.caption = caption
        self.tint, self.border = tint, border
        self.pad = 6

    def _line_h(self):
        return self.style.leading

    def wrap(self, aw, ah):
        self.height = self.pad * 2 + self._line_h() * max(1, len(self.lines))
        return (self.width, self.height)

    def split(self, aw, ah):
        lh = self._line_h()
        avail = ah - self.pad * 2
        if avail < lh * 3:
            return []
        keep = int(avail // lh)
        if keep >= len(self.lines):
            return [self]
        a = CodeBox(self.lines[:keep], self.width, self.style, None, self.tint, self.border)
        b = CodeBox(self.lines[keep:], self.width, self.style, self.caption,
                    self.tint, self.border)
        return [a, b]

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.4)
        c.rect(0, 0, self.width, self.height, stroke=1, fill=0)
        c.restoreState()
        c.setFont(self.style.fontName, self.style.fontSize)
        c.setFillColor(self.style.textColor)
        lh = self._line_h()
        y = self.height - self.pad - self.style.fontSize
        maxchars = int((self.width - self.pad * 2) /
                       pdfmetrics.stringWidth("M", self.style.fontName,
                                              self.style.fontSize))
        for ln in self.lines:
            t = ln.rstrip("\n")
            if len(t) > maxchars:
                t = t[:maxchars - 1] + "\u2026"
            c.drawString(self.pad, y, t)
            y -= lh


# --------------------------------------------------------------------------- #
# Source parsing
# --------------------------------------------------------------------------- #
class Doc:
    def __init__(self):
        self.cover = {}
        self.flows = []


def parse(src: str, story: list, doc_state: dict):
    lines = src.split("\n")
    i, n = 0, len(lines)
    cover = {}

    def flush_para(buf):
        if buf:
            txt = " ".join(x.strip() for x in buf).strip()
            if txt:
                story.append(Paragraph(inline(txt), S["body"]))
            buf.clear()

    para: list[str] = []

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        st = line.strip()

        # ---- cover block
        if st == "%%COVER":
            i += 1
            while i < n and lines[i].strip() != "%%END":
                if ":" in lines[i]:
                    k, v = lines[i].split(":", 1)
                    cover.setdefault(k.strip(), []).append(v.strip())
                i += 1
            i += 1
            doc_state["cover"] = cover
            continue

        # ---- forced page break
        if st == "<<<PAGEBREAK>>>":
            flush_para(para)
            story.append(PageBreak())
            i += 1
            continue

        # ---- horizontal rule
        if st == "---":
            flush_para(para)
            story.append(Rule(CONTENT_W))
            i += 1
            continue

        # ---- fenced code / diagram
        if st.startswith("```"):
            flush_para(para)
            lang = st[3:].strip().lower()
            i += 1
            block = []
            while i < n and not lines[i].rstrip().startswith("```"):
                block.append(sanitize(lines[i].rstrip("\n")))
                i += 1
            i += 1
            caption = None
            if i < n and lines[i].strip().startswith("^^"):
                caption = lines[i].strip()[2:].strip()
                i += 1
            style = S["diag"] if lang in ("diagram", "figure", "flow") else S["code"]
            tint = colors.white
            box = CodeBox(block, CONTENT_W, style, caption, tint, CODE_BR)
            story.append(Spacer(1, 3))
            story.append(box)
            if caption:
                story.append(Paragraph(inline(caption), S["cap"]))
            else:
                story.append(Spacer(1, 7))
            continue

        # ---- callout
        m = re.match(r"^:::(\w+)\s*(.*)$", st)
        if m:
            flush_para(para)
            kind = m.group(1).lower()
            kind = ALIAS.get(kind, kind)
            title = m.group(2).strip()
            if kind not in CALLOUTS:
                sys.stderr.write(f"WARN unknown callout kind: {kind}\n")
                kind = "key"
            i += 1
            block = []
            while i < n and lines[i].strip() != ":::":
                block.append(lines[i])
                i += 1
            i += 1
            sub: list = []
            parse_block("\n".join(block), sub)
            inner_w = CONTENT_W - 3.0 - 16
            sub2 = []
            for f in sub:
                if isinstance(f, CodeBox):
                    f.width = inner_w
                if isinstance(f, Rule):
                    f.width = inner_w
                sub2.append(f)
            story.append(Spacer(1, 4))
            story.append(make_callout(kind, title, sub2, CONTENT_W))
            story.append(Spacer(1, 8))
            continue

        # ---- table
        if st.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|$",
                                                         lines[i + 1].strip()):
            flush_para(para)
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            caption = None
            if i < n and lines[i].strip().startswith("^^"):
                caption = lines[i].strip()[2:].strip()
                i += 1
            story.extend(make_table(rows, caption))
            continue

        # ---- headings
        if st.startswith("#"):
            flush_para(para)
            level = len(st) - len(st.lstrip("#"))
            text = st[level:].strip()
            story.extend(make_heading(level, text))
            i += 1
            continue

        # ---- lists
        if re.match(r"^\s*([-*]|\d+\.)\s+", raw):
            flush_para(para)
            items, ordered = [], bool(re.match(r"^\s*\d+\.\s", raw))
            while i < n and (re.match(r"^\s*([-*]|\d+\.)\s+", lines[i])
                             or (lines[i].startswith("    ") and lines[i].strip()
                                 and items)):
                cur = lines[i]
                if re.match(r"^\s*([-*]|\d+\.)\s+", cur):
                    indent = len(cur) - len(cur.lstrip())
                    body = re.sub(r"^\s*([-*]|\d+\.)\s+", "", cur).strip()
                    items.append([indent, body])
                else:
                    items[-1][1] += " " + cur.strip()
                i += 1
            story.extend(make_list(items, ordered))
            continue

        # ---- blank
        if not st:
            flush_para(para)
            i += 1
            continue

        para.append(line)
        i += 1

    flush_para(para)


def parse_block(src: str, out: list):
    """Parse a nested block (inside a callout) - no headings/TOC side-effects."""
    sub_state = {}
    parse(src, out, sub_state)


_FIRST_PART = [True]


def make_heading(level, text):
    out = []
    if level == 1:
        # PART divider page
        m = re.match(r"^(PART\s+\d+)\s*[\u2014\-:]\s*(.*)$", text)
        num = m.group(1) if m else ""
        title = m.group(2) if m else text
        sub = ""
        if "||" in title:
            title, sub = [x.strip() for x in title.split("||", 1)]
        if not _FIRST_PART[0]:
            out.append(PageBreak())
        _FIRST_PART[0] = False
        out.append(Bookmark("part", text))
        out.append(Spacer(1, 58 * mm))
        if num:
            out.append(Paragraph(inline(num), S["part_no"]))
        h = HeadingFlowable(inline(title), S["part"], 0, num or title,
                            toc_text=inline((num + " \u2014 " if num else "") + title))
        out.append(h)
        out.append(Rule(60 * mm, 0.8, colors.black, 8))
        if sub:
            out.append(Spacer(1, 6))
            out.append(Paragraph(inline(sub), S["part_sub"]))
    elif level == 2:
        out.append(PageBreak())
        h = HeadingFlowable(inline(text), S["h1"], 1, text)
        out.append(h)
        out.append(Rule(CONTENT_W, 0.8, colors.black, 3))
        out.append(Spacer(1, 5))
    elif level == 3:
        out.append(CondPageBreak(34 * mm))
        out.append(HeadingFlowable(inline(text), S["h2"], 2, None))
    else:
        out.append(CondPageBreak(24 * mm))
        out.append(Paragraph(inline(text), S["h3"]))
    return out


def split_row(r):
    cells = r.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def make_table(rows, caption=None):
    header = split_row(rows[0])
    body = [split_row(r) for r in rows[2:]]
    ncol = len(header)
    body = [(r + [""] * ncol)[:ncol] for r in body]

    # ---- column widths: min = widest single word, preferred = full text ----
    def plain(t):
        t = sanitize(t)
        return re.sub(r"[*`]", "", t)

    def w_of(t, bold=False):
        f = "Head-Bold" if bold else "Body"
        sz = 8.2 if bold else 8.5
        return pdfmetrics.stringWidth(plain(t), f, sz)

    PADX = 9.0
    minw, prefw = [], []
    for c in range(ncol):
        col = [(header[c], True)] + [(r[c], False) for r in body]
        mw = 0.0
        pw = 0.0
        for txt, bold in col:
            words = plain(txt).split() or [""]
            mw = max(mw, max(w_of(x, bold) for x in words))
            pw = max(pw, w_of(txt, bold))
        minw.append(min(mw + PADX, 46 * mm))
        prefw.append(min(max(pw + PADX, mw + PADX), 95 * mm))
    if sum(minw) > CONTENT_W:
        k = CONTENT_W / sum(minw)
        minw = [w * k for w in minw]
        prefw = [max(a, b) for a, b in zip(minw, prefw)]
    slack = CONTENT_W - sum(minw)
    extra = [max(0.0, p - m) for p, m in zip(prefw, minw)]
    tot_extra = sum(extra)
    if tot_extra <= 0:
        widths = [m + slack / ncol for m in minw]
    else:
        share = min(1.0, slack / tot_extra)
        widths = [m + e * share for m, e in zip(minw, extra)]
        left = CONTENT_W - sum(widths)
        if left > 0.5:
            widths = [w + left / ncol for w in widths]

    def cellstyle(txt, col):
        numeric = bool(re.match(r"^[\-+]?[\d.,%\s\u2212/x]+$", txt.strip())) and txt.strip()
        return S["td_m"] if numeric else S["td"]

    data = [[Paragraph(inline(h), S["th"]) for h in header]]
    for r in body:
        data.append([Paragraph(inline(c), cellstyle(c, k)) for k, c in enumerate(r)])

    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.0),
        ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.black),
    ]
    t.setStyle(TableStyle(style))
    out = [Spacer(1, 4), t]
    if caption:
        out.append(Paragraph(inline(caption), S["cap"]))
    else:
        out.append(Spacer(1, 9))
    return out


def make_list(items, ordered):
    flows = []
    top = [(ind, txt) for ind, txt in items]
    lf = []
    k = 0
    while k < len(top):
        ind, txt = top[k]
        children = []
        j = k + 1
        while j < len(top) and top[j][0] > ind:
            children.append(top[j])
            j += 1
        para = Paragraph(inline(txt), S["li"])
        if children:
            sub = ListFlowable(
                [ListItem(Paragraph(inline(t), S["li"]), leftIndent=10)
                 for _, t in children],
                bulletType="bullet", start="circle", leftIndent=14,
                bulletFontName="Body", bulletFontSize=7)
            lf.append(ListItem([para, sub], leftIndent=14))
        else:
            lf.append(ListItem(para, leftIndent=14))
        k = j
    flows.append(ListFlowable(lf,
                              bulletType="1" if ordered else "bullet",
                              start="1" if ordered else "square",
                              bulletFormat="%s." if ordered else None,
                              leftIndent=15, bulletFontName="Body",
                              bulletFontSize=8 if not ordered else 9.6,
                              bulletOffsetY=0))
    flows.append(Spacer(1, 5))
    return flows


# --------------------------------------------------------------------------- #
# Document template
# --------------------------------------------------------------------------- #
class Handbook(BaseDocTemplate):
    def __init__(self, path, title, **kw):
        BaseDocTemplate.__init__(self, path, pagesize=A4,
                                 leftMargin=M_L, rightMargin=M_R,
                                 topMargin=M_T, bottomMargin=M_B,
                                 title=title, author="Final Year Project",
                                 subject="Complete technical and viva handbook",
                                 **kw)
        frame = Frame(M_L, M_B, CONTENT_W, PAGE_H - M_T - M_B, id="main",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        cover_frame = Frame(M_L, M_B, CONTENT_W, PAGE_H - M_T - M_B, id="cover",
                            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover_frame], onPageEnd=self._cover_page),
            PageTemplate(id="front", frames=[frame], onPageEnd=self._front_page),
            PageTemplate(id="body", frames=[frame], onPageEnd=self._body_page),
        ])
        self.header = ""
        self.part = ""
        self.body_start = None
        self.doc_title = title

    def beforeDocument(self):
        """multiBuild runs several passes; each must start with clean state."""
        self.header = ""
        self.part = ""
        self.body_start = None

    # --- decoration ------------------------------------------------------- #
    def _cover_page(self, canv, doc):
        pass

    def _front_page(self, canv, doc):
        p = canv.getPageNumber() - 1
        canv.saveState()
        canv.setFont("Body", 8.5)
        canv.setFillColor(INK_SOFT)
        canv.drawCentredString(PAGE_W / 2, M_B - 9 * mm, _roman(p))
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(M_L, PAGE_H - M_T + 6 * mm, PAGE_W - M_R, PAGE_H - M_T + 6 * mm)
        canv.setFont("Body", 8.5)
        canv.drawString(M_L, PAGE_H - M_T + 8.4 * mm, self.doc_title.upper())
        canv.restoreState()

    def _body_page(self, canv, doc):
        raw = canv.getPageNumber()
        num = raw - (self.body_start - 1) if self.body_start else raw
        canv.saveState()
        # header rule + text
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(M_L, PAGE_H - M_T + 6 * mm, PAGE_W - M_R, PAGE_H - M_T + 6 * mm)
        canv.setFont("Body", 8.5)
        canv.setFillColor(INK_SOFT)
        left = sanitize(self.part or self.doc_title)
        if len(left) > 46:
            left = left[:45].rstrip() + "\u2026"
        canv.drawString(M_L, PAGE_H - M_T + 8.4 * mm, left)
        right = sanitize(self.header or "")
        if len(right) > 62:
            right = right[:61].rstrip() + "\u2026"
        canv.drawRightString(PAGE_W - M_R, PAGE_H - M_T + 8.4 * mm, right)
        # footer
        canv.setStrokeColor(RULE)
        canv.line(M_L, M_B - 6 * mm, PAGE_W - M_R, M_B - 6 * mm)
        canv.setFont("Body", 8.5)
        canv.setFillColor(INK_SOFT)
        canv.drawString(M_L, M_B - 10.2 * mm,
                        "My Final Year Project \u2014 Technical & Viva Handbook")
        canv.drawRightString(PAGE_W - M_R, M_B - 10.2 * mm, str(num))
        canv.restoreState()

    # --- TOC + header tracking --------------------------------------------- #
    def afterFlowable(self, flowable):
        if isinstance(flowable, Bookmark):
            if flowable.kind == "bodystart":
                self.body_start = self.canv.getPageNumber()
            elif flowable.kind == "part":
                self.part = flowable.text
            return
        if isinstance(flowable, HeadingFlowable):
            raw = self.canv.getPageNumber()
            num = raw - (self.body_start - 1) if self.body_start else raw
            txt = re.sub(r"<[^>]+>", "", flowable.toc_text)
            self.notify("TOCEntry", (flowable.toc_level, txt, num))
            if flowable.header_text:
                if flowable.toc_level == 0:
                    self.part = flowable.header_text
                    self.header = ""
                else:
                    self.header = flowable.header_text
            self.canv.bookmarkPage(f"h{id(flowable)}")
            self.canv.addOutlineEntry(txt[:110], f"h{id(flowable)}",
                                      level=min(flowable.toc_level, 2), closed=True)


def _roman(n: int) -> str:
    if n <= 0:
        return ""
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"),
            (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"),
            (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


# --------------------------------------------------------------------------- #
# Cover
# --------------------------------------------------------------------------- #
def cover_flows(cv):
    def g(k, default=""):
        v = cv.get(k)
        return v[0] if v else default

    out = [Spacer(1, 26 * mm)]
    out.append(Paragraph(inline(g("kicker", "FINAL YEAR ENGINEERING PROJECT")),
                         S["cv_kick"]))
    out.append(Spacer(1, 8))
    out.append(Paragraph(inline(g("title")), S["cv_title"]))
    out.append(Spacer(1, 6))
    out.append(Rule(CONTENT_W * 0.35, 0.8, colors.black, 6, center=True))
    out.append(Spacer(1, 8))
    out.append(Paragraph(inline(g("subtitle")), S["cv_sub"]))
    out.append(Spacer(1, 16 * mm))
    for ln in cv.get("line", []):
        out.append(Paragraph(inline(ln), S["cv_meta"]))
    out.append(Spacer(1, 14 * mm))
    box = [[Paragraph(inline(x), S["td"]) for x in split_row(r)]
           for r in cv.get("fact", [])]
    if box:
        t = Table(box, colWidths=[CONTENT_W * 0.34, CONTENT_W * 0.46], hAlign="CENTER")
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        out.append(t)
    out.append(Spacer(1, 12 * mm))
    for ln in cv.get("foot", []):
        out.append(Paragraph(inline(ln), S["cv_small"]))
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    src_path, out_path = sys.argv[1], sys.argv[2]
    register_fonts()
    build_styles()
    src = Path(src_path).read_text(encoding="utf-8")

    state = {}
    body: list = []
    parse(src, body, state)
    cv = state.get("cover", {})
    title = (cv.get("title", ["Project Handbook"])[0])

    doc = Handbook(out_path, "My Final Year Project")

    toc = TableOfContents()
    toc.levelStyles = [S["toc0"], S["toc1"], S["toc2"]]
    toc.dotsMinLevel = 0

    story: list = []
    story.append(NextPageTemplate("front"))
    story.extend(cover_flows(cv))
    story.append(PageBreak())

    story.append(Paragraph("Contents", S["h1"]))
    story.append(Rule(CONTENT_W, 0.8, colors.black, 3))
    story.append(Spacer(1, 6))
    story.append(toc)
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    story.append(Bookmark("bodystart"))
    story.extend(body)

    doc.multiBuild(story)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

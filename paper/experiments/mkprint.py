"""Build an IEEE-style two-column print HTML from the verified web version.

Content is lifted verbatim from paper_web.html so the print PDF and the reading
version cannot drift. Only presentation changes.
"""
import re, os
SRC = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/paper_web.html"
OUT = "/Users/bilalashfaque/Desktop/Silent-Video-Project/paper/paper_print.html"
html = open(SRC).read()

body = html.split('<div class="sheet">', 1)[1].rsplit('</div>\n</div>', 1)[0]

# --- strip web-only devices -------------------------------------------------
# readout tiles: pure web furniture, the numbers all appear in the prose
body = re.sub(r'<div class="readout">.*?</div>\s*</div>\s*', '', body, flags=re.S)
body = re.sub(r'\s*<div class="readout">.*?\n\s*</div>\n', '\n', body, flags=re.S)

# notes -> IEEE-appropriate emphasised paragraph with a run-in label
def note_repl(m):
    inner = m.group(2)
    lbl = re.search(r'<span class="lbl">(.*?)</span>', inner, re.S)
    label = lbl.group(1).strip() if lbl else ""
    inner = re.sub(r'<span class="lbl">.*?</span>\s*', '', inner, flags=re.S)
    paras = re.findall(r'<p>(.*?)</p>', inner, flags=re.S)
    out = ['<div class="callout">']
    for i, p in enumerate(paras):
        if i == 0 and label:
            out.append(f'<p><span class="runin">{label}.</span> {p.strip()}</p>')
        else:
            out.append(f'<p>{p.strip()}</p>')
    out.append('</div>')
    return "\n".join(out)
body = re.sub(r'<div class="note( warn)?">(.*?)</div>', note_repl, body, flags=re.S)

# figure width classes -> column-span control
body = body.replace('<figure class="wide">', '<figure class="span">')

# wide tables (>=5 cols) span both columns
def tbl_span(m):
    block = m.group(0)
    ncol = block.split('</tr>')[0].count('<th')
    return block.replace('<div class="tbl">', '<div class="tbl span">') if ncol >= 5 else block
body = re.sub(r'<div class="tbl">.*?</div>\s*</div>', tbl_span, body, flags=re.S)

# abstract/terms come out of the two-column flow
body = body.replace('<section class="abstract">', '<section class="abstract span">')
body = body.replace('<section class="terms">', '<section class="terms span">')

CSS = r"""
@page { size: Letter; margin: 0.75in 0.625in 1in 0.625in; }
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:"Times New Roman",Times,serif;
  font-size:10pt; line-height:1.16; color:#000; background:#fff;
  text-align:justify; hyphens:auto; -webkit-hyphens:auto;
}
.doc{column-count:2; column-gap:0.25in; column-fill:auto}
p{margin:0 0 0 0; text-indent:0.2in}
p.first, .abstract p, .callout p, figcaption, .tbl .cap{text-indent:0}
h2.sec + p, h3.sub + p, ul + p, ol + p, .eq + p, figure + p, .tbl + p, .callout + p{text-indent:0}

/* ---- title block ---- */
.titleblock{column-span:all; text-align:center; margin:0 0 14pt}
.titleblock h1{
  font-size:20pt; font-weight:400; line-height:1.12; margin:0 0 10pt;
  font-family:"Times New Roman",Times,serif;
}
.titleblock h1 .sub{display:block; font-size:.72em; margin-top:5pt}
.titleblock .authors{font-size:11pt; line-height:1.3; margin:0}
.titleblock .authors .name{font-size:11pt}
.titleblock .authors .aff{font-style:italic; font-size:10pt}
.titleblock .authors .todo{
  font-family:"Courier New",monospace; font-size:8.5pt;
  border:0.5pt solid #999; padding:0 3pt;
}

/* ---- abstract / index terms ---- */
.abstract, .terms{column-span:all; margin:0 0 9pt}
.abstract h2, .terms h2{display:none}
.abstract p{font-size:9pt; line-height:1.2; font-weight:bold; margin:0}
.abstract p::before{content:"Abstract\2014"; font-style:italic; font-weight:bold}
.terms .list{font-size:9pt; font-weight:bold}
.terms .list::before{content:"Index Terms\2014"; font-style:italic}
.terms .list span{display:inline}
.terms .list span::after{content:", "}
.terms .list span:last-child::after{content:"."}

/* ---- headings ---- */
h2.sec{
  font-size:10pt; font-weight:400; font-variant:small-caps;
  text-align:center; margin:11pt 0 4pt; padding:0; border:none;
  display:block; break-after:avoid; page-break-after:avoid;
}
h2.sec .num{font-variant:normal; font-family:inherit; color:#000; min-width:0}
h2.sec .num::after{content:". "}
h3.sub{
  font-size:10pt; font-weight:400; font-style:italic;
  text-align:left; margin:8pt 0 3pt; break-after:avoid; page-break-after:avoid;
}
h3.sub .n{font-family:inherit; color:#000; font-style:italic; margin-right:.3em}

/* ---- lists ---- */
ul,ol{margin:4pt 0 4pt 0; padding-left:0.24in}
li{margin:0 0 2pt; text-align:justify}

/* ---- code / inline ---- */
code,.m{font-family:"Courier New",monospace; font-size:8.6pt; background:none; padding:0}
strong{font-weight:bold}

/* ---- figures ---- */
figure{margin:8pt 0 9pt; break-inside:avoid; page-break-inside:avoid}
figure.span{column-span:all}
figure img{display:block; width:100%; height:auto; border:none}
figcaption{font-size:8pt; line-height:1.22; margin-top:4pt; text-align:justify}
figcaption b{font-weight:400}

/* ---- tables ---- */
.tbl{margin:8pt 0 9pt; break-inside:avoid; page-break-inside:avoid}
.tbl.span{column-span:all}
.tbl .cap{
  font-size:8pt; text-align:center; margin:0 0 3pt;
  font-variant:small-caps; line-height:1.25;
}
.tbl .cap b{font-weight:400}
.scroll{overflow:visible; border:none}
table{border-collapse:collapse; width:100%; font-size:8pt; font-family:"Times New Roman",Times,serif}
th,td{padding:1.6pt 4pt; text-align:left; white-space:normal}
thead th{
  border-top:0.9pt solid #000; border-bottom:0.5pt solid #000;
  background:none; font-weight:bold; font-size:8pt;
  letter-spacing:0; text-transform:none; color:#000;
}
tbody tr:last-child td{border-bottom:0.9pt solid #000}
tbody tr + tr td{border-top:none}
td.n,th.n{text-align:right}
tbody tr.group td{
  background:none; font-style:italic; font-weight:400;
  text-transform:none; letter-spacing:0; color:#000;
  border-top:0.4pt solid #999; font-size:8pt;
}
.best,.bad{font-weight:bold; color:#000}
.mono{font-family:"Times New Roman",Times,serif; font-size:8pt}

/* ---- callouts (were coloured notes on the web) ---- */
.callout{
  margin:6pt 0 7pt; padding:5pt 7pt;
  border-left:1.5pt solid #000; background:none;
  break-inside:avoid; page-break-inside:avoid;
}
.callout p{font-size:9pt; line-height:1.2; margin:0}
.callout p + p{margin-top:3pt}
.callout .runin{font-style:italic; font-weight:bold}

/* ---- equation ---- */
.eq{
  margin:6pt 0; padding:0; background:none; border-radius:0;
  font-family:"Times New Roman",Times,serif; font-size:10pt;
  display:flex; align-items:center; justify-content:space-between; gap:12pt;
  break-inside:avoid;
}
.eq > span:first-child{flex:1; text-align:center; font-style:italic}
.eq .tag{color:#000; font-size:10pt; font-style:normal}

/* ---- references ---- */
.refs ol{padding-left:0; display:block; counter-reset:ref}
.refs li{
  display:block; position:relative;
  padding-left:0.22in; margin:0 0 2.5pt;
  font-size:8pt; line-height:1.2; text-align:justify;
  counter-increment:ref;
}
.refs li::before{
  content:"[" counter(ref) "]"; position:absolute; left:0;
  font-family:"Times New Roman",Times,serif; font-size:8pt; color:#000;
}
.refs li i{font-style:italic}
h2.sec .num{}
"""

doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Reconstructing Audio from Silent Video</title>
<style>{CSS}</style></head>
<body>
<div class="doc">
  <div class="titleblock">
    <h1>Reconstructing Audio from Silent Video
      <span class="sub">A Three-Path System for Speech, Foley and Surface-Vibration
      Recovery on Consumer Hardware</span></h1>
    <p class="authors">
      <span class="name">Bilal Ashfaque</span><br>
      <span class="aff">Department of <span class="todo">[Department]</span>,
      <span class="todo">[Institution]</span></span><br>
      <span class="aff"><span class="todo">[City, Country]</span></span><br>
      bufferoverflow55@gmail.com
    </p>
  </div>
{body}
</div>
</body></html>
"""
open(OUT, "w").write(doc)
print("written", OUT, f"{os.path.getsize(OUT)/1024/1024:.2f} MB")
for probe in ("readout", "{{"):
    print(f"  residual '{probe}':", doc.count(probe))
print("  figures:", doc.count("<figure"), " span-figures:", doc.count('figure class="span"'))
print("  tables :", doc.count("<table"), " span-tables :", doc.count('tbl span'))
print("  callouts:", doc.count('class="callout"'))

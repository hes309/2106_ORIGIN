#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "2106_ORIGIN_Finalised Chinese version.html"
COVER = ROOT / "ebook_output" / "2106_ORIGIN_V14_正式封面.png"
OUT_DIR = ROOT / "ebook_output"
BUILD_DIR = OUT_DIR / "_v14_epub_build"
OUT_EPUB = OUT_DIR / "2106_ORIGIN_V14_Finalised_Chinese.epub"
FORMULA_IMAGE_DIR = OUT_DIR / "v14_formula_images"

TITLE = "2106：起源"
SUBTITLE = "2106: ORIGIN"
AUTHOR = "e"
LANG = "zh-CN"


@dataclass
class Paragraph:
    text: str
    classes: set[str] = field(default_factory=set)
    image_src: str | None = None


@dataclass
class Section:
    kind: str
    title: str
    filename: str
    paragraphs: list[Paragraph] = field(default_factory=list)


class ParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[Paragraph] = []
        self._in_p = False
        self._classes: set[str] = set()
        self._parts: list[str] = []
        self._in_figure = False
        self._figure_classes: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            values = dict(attrs)
            self._in_p = True
            self._classes = set((values.get("class") or "").split())
            self._parts = []
        elif tag == "figure":
            values = dict(attrs)
            self._in_figure = True
            self._figure_classes = set((values.get("class") or "").split())
        elif tag == "img" and self._in_figure:
            values = dict(attrs)
            # The finalised single-file HTML embeds images as data URIs while
            # preserving their original local paths in data-source.
            src = values.get("data-source") or values.get("src")
            if src:
                self.paragraphs.append(
                    Paragraph(text=values.get("alt") or "", classes=self._figure_classes, image_src=src)
                )
        elif tag == "br" and self._in_p:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_p:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._in_p:
            text = "".join(self._parts).replace("\xa0", " ").strip()
            self.paragraphs.append(Paragraph(text=text, classes=self._classes))
            self._in_p = False
            self._classes = set()
            self._parts = []
        elif tag == "figure":
            self._in_figure = False
            self._figure_classes = set()


FORMULAS = {
    r"$$\mathcal{CV}_\infty = \left(\frac{E_f}{E_0}\right)^\alpha \cdot \left(\frac{K}{K_0}\right)^\beta \cdot \left(\frac{C}{C_0}\right)^\gamma \cdot \mathcal{T}(\Theta)$$":
        "CV∞ = (E_f/E_0)^α · (K/K_0)^β · (C/C_0)^γ · T(Θ)",
    r"$$\mathcal{T}(\Theta) = 1,\qquad \Theta \geq \Theta_c$$":
        "T(Θ) = 1，Θ ≥ Θ_c",
    r"$$\mathcal{T}(\Theta) = \left(\frac{\Theta}{\Theta_c}\right)^\zeta,\qquad \Theta \lt \Theta_c$$":
        "T(Θ) = (Θ/Θ_c)^ζ，Θ < Θ_c",
    r"$$\Theta = \frac{\text{有效连接数}}{\text{节点数}} \cdot \frac{1}{1+\tau/\tau_{\mathrm{ref}}}$$":
        "Θ = 有效连接数/节点数 · 1/(1 + τ/τ_ref)",
    r"$$\mathcal{CV} = k(\mathbf r,t) \cdot \left(\frac{E_f}{E_0}\right)^\alpha \cdot \left(\frac{K}{K_0}\right)^\beta \cdot \left(\frac{C}{C_0}\right)^\gamma \cdot \left(\frac{Q}{Q_0}\right)^\delta$$":
        "CV = k(r,t) · (E_f/E_0)^α · (K/K_0)^β · (C/C_0)^γ · (Q/Q_0)^δ",
    r"$$C^* = \frac{c \cdot Q_{\mathrm{min}}}{\lambda_0 \cdot \ln\!\left(V_0/V_{\mathrm{min}}\right)}$$":
        "C* = c · Q_min / [λ_0 · ln(V_0/V_min)]",
    r"$$\Omega(n) = \frac{1}{1+\kappa\ln n}$$":
        "Ω(n) = 1 / (1 + κ ln n)",
    r"$$\mathcal{CR} = Q^a \cdot \left(\frac{1}{1+S_{\mathrm{rate}}}\right)^b \cdot (1+g_K)^c \cdot \left(1-P_{\mathrm{def}}e^{-\phi\Delta t}\right)^d$$":
        "CR = Q^a · [1/(1 + S_rate)]^b · (1 + g_K)^c · (1 − P_def e^(−φΔt))^d",
    r"$$\frac{Q_{\text{分布式}}}{Q_{\text{中央式}}} = \left(\frac{C}{C^*}\right)^\varphi,\qquad C > C^*,\qquad \varphi > 0$$":
        "Q_分布式 / Q_中央式 = (C/C*)^φ，C > C*，φ > 0",
}

FORMULA_IMAGE_IDS = {
    formula: image_id
    for formula, image_id in zip(
        FORMULAS,
        ["f01", "f02", "f03", "f04", "f05", "f06", "f07", "f08", "f09"],
    )
}


def parse_sections() -> tuple[list[Section], str]:
    parser = ParagraphParser()
    parser.feed(SOURCE.read_text(encoding="utf-8"))

    sections: list[Section] = []
    current: Section | None = None
    chapter_no = 0
    started = False
    epigraph = "欲了解宇宙的本质，解答终极问题，必需拓展意识的边界与维度。"
    volume_starts = {
        1: "第一卷：黑色一分钟",
        13: "第二卷：天穹觉醒",
        24: "第三卷：苍穹之战",
    }

    for para in parser.paragraphs:
        text = para.text
        if "heading" in para.classes and re.match(r"^第[一二三]卷[： ]", text):
            continue
        if "heading" in para.classes and re.match(r"^第[一二三四五六七八九十百]+章[：]", text):
            chapter_no += 1
            if chapter_no in volume_starts:
                volume_index = len([s for s in sections if s.kind == "volume"]) + 1
                sections.append(Section("volume", volume_starts[chapter_no], f"vol{volume_index:02d}.xhtml"))
            started = True
            current = Section("chapter", text, f"ch{chapter_no:02d}.xhtml")
            sections.append(current)
            continue
        if started and current and text:
            current.paragraphs.append(para)

    return sections, epigraph


def render_paragraph(para: Paragraph) -> str:
    if para.image_src:
        image_name = Path(para.image_src).name
        alt = html.escape(para.text, quote=True)
        classes = "illustration landscape" if "landscape" in para.classes else "illustration"
        return f'<div class="{classes}"><img src="../images/illustrations/{image_name}" alt="{alt}"/></div>'
    if "formula" in para.classes:
        image_id = FORMULA_IMAGE_IDS.get(para.text)
        if image_id:
            alt = html.escape(FORMULAS[para.text], quote=True)
            return f'<div class="formula"><img src="../images/formulas/{image_id}.png" alt="{alt}"/></div>'
    escaped = html.escape(para.text, quote=False)
    escaped = escaped.replace(
        r"$C_{\mathrm{eff}} = f(K,\tau)$",
        '<span class="inline-formula">C<sub>eff</sub> = f(K, τ)</span>',
    )
    escaped = escaped.replace(
        r"$e^{i\pi}+1=0$",
        '<span class="inline-formula">e<sup>iπ</sup> + 1 = 0</span>',
    )
    if "center" in para.classes:
        return f'<p class="center">{escaped}</p>'
    return f"<p>{escaped}</p>"


XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../styles.css"/>
</head>
<body>
{body}
</body>
</html>
"""


CSS = """
html, body { margin: 0; padding: 0; }
body { font-family: "Songti SC", "Noto Serif CJK SC", serif; line-height: 1.78; color: #111; padding: 0 5%; }
p { margin: 0 0 0.85em; text-indent: 2em; text-align: justify; }
h1, h2 { font-family: "Heiti SC", "Noto Sans CJK SC", sans-serif; text-align: center; line-height: 1.35; }
h1 { font-size: 1.65em; margin: 42% 0 0; }
h2 { font-size: 1.35em; margin: 2.5em 0 1.8em; }
.cover { margin: 0; padding: 0; text-align: center; }
.cover img { display: block; width: 100%; height: auto; max-height: 100vh; object-fit: contain; }
.titlepage { text-align: center; margin-top: 30%; }
.titlepage h1 { margin: 0 0 1.2em; font-size: 1.8em; }
.titlepage p, .epigraph p, .center { text-indent: 0; text-align: center; }
.titlepage .subtitle { font-family: sans-serif; letter-spacing: 0.12em; margin-bottom: 5em; }
.epigraph { margin: 30% 8% 0; }
.formula { margin: 1.15em 0; text-align: center; }
.formula img { display: block; width: 100%; max-width: 54em; height: auto; margin: 0 auto; }
.illustration { margin: 1.3em 0; text-align: center; break-inside: avoid; page-break-inside: avoid; }
.illustration img { display: block; width: auto; max-width: 100%; max-height: 92vh; margin: 0 auto; }
.illustration.landscape img { width: 100%; height: auto; max-height: none; }
.inline-formula { font-family: "Times New Roman", "STIX Two Math", serif; white-space: nowrap; }
.inline-formula sub, .inline-formula sup { line-height: 0; }
nav ol { list-style: none; padding-left: 0; }
nav ol ol { padding-left: 1.4em; }
nav li { margin: 0.55em 0; }
nav a { color: inherit; text-decoration: none; }
"""


def write_xhtml(path: Path, title: str, body: str) -> None:
    path.write_text(XHTML.format(title=html.escape(title), body=body), encoding="utf-8")


def build() -> None:
    sections, epigraph = parse_sections()
    chapters = [s for s in sections if s.kind == "chapter"]
    volumes = [s for s in sections if s.kind == "volume"]
    if len(chapters) != 35 or len(volumes) != 3:
        raise RuntimeError(f"目录结构异常：{len(volumes)}卷，{len(chapters)}章")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    text_dir = BUILD_DIR / "OEBPS" / "text"
    image_dir = BUILD_DIR / "OEBPS" / "images"
    meta_dir = BUILD_DIR / "META-INF"
    text_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)

    (BUILD_DIR / "mimetype").write_text("application/epub+zip", encoding="utf-8")
    (meta_dir / "container.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
        "</container>\n",
        encoding="utf-8",
    )
    shutil.copy2(COVER, image_dir / "cover.png")
    formula_target = image_dir / "formulas"
    formula_target.mkdir()
    for formula_id in sorted(set(FORMULA_IMAGE_IDS.values())):
        shutil.copy2(FORMULA_IMAGE_DIR / f"{formula_id}.png", formula_target / f"{formula_id}.png")
    illustration_source = OUT_DIR / "illustrations"
    illustration_target = image_dir / "illustrations"
    illustration_target.mkdir()
    for illustration in sorted(illustration_source.glob("*.png")):
        shutil.copy2(illustration, illustration_target / illustration.name)
    (BUILD_DIR / "OEBPS" / "styles.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    write_xhtml(text_dir / "cover.xhtml", "封面", '<section class="cover"><img src="../images/cover.png" alt="2106：起源 封面"/></section>')
    write_xhtml(
        text_dir / "title.xhtml",
        TITLE,
        f'<section class="titlepage"><h1>{TITLE}</h1><p class="subtitle">{SUBTITLE}</p><p>{AUTHOR}</p></section>',
    )
    write_xhtml(
        text_dir / "epigraph.xhtml",
        "题记",
        f'<section class="epigraph"><p>{epigraph}</p>'
        '<p><i>To understand the nature of the universe and answer the ultimate questions, '
        'we must expand the boundaries and dimensions of consciousness.</i></p></section>',
    )

    for section in sections:
        tag = "h1" if section.kind == "volume" else "h2"
        body = [f"<{tag}>{html.escape(section.title)}</{tag}>"]
        body.extend(render_paragraph(p) for p in section.paragraphs)
        write_xhtml(text_dir / section.filename, section.title, "\n".join(body))

    nav_parts = ['<nav epub:type="toc" id="toc"><h2>目录</h2><ol>']
    nav_parts.extend([
        '<li><a href="text/cover.xhtml">封面</a></li>',
        '<li><a href="text/title.xhtml">题名页</a></li>',
        '<li><a href="text/epigraph.xhtml">题记</a></li>',
    ])
    for volume in volumes:
        nav_parts.append(f'<li><a href="text/{volume.filename}">{html.escape(volume.title)}</a><ol>')
        start = sections.index(volume) + 1
        for section in sections[start:]:
            if section.kind == "volume":
                break
            nav_parts.append(f'<li><a href="text/{section.filename}">{html.escape(section.title)}</a></li>')
        nav_parts.append("</ol></li>")
    nav_parts.append("</ol></nav>")
    write_xhtml(BUILD_DIR / "OEBPS" / "nav.xhtml", "目录", "\n".join(nav_parts).replace("../styles.css", "styles.css"))
    nav_path = BUILD_DIR / "OEBPS" / "nav.xhtml"
    nav_path.write_text(nav_path.read_text(encoding="utf-8").replace('href="../styles.css"', 'href="styles.css"'), encoding="utf-8")

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="css" href="styles.css" media-type="text/css"/>',
        '<item id="cover-image" href="images/cover.png" media-type="image/png" properties="cover-image"/>',
        '<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="title" href="text/title.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="epigraph" href="text/epigraph.xhtml" media-type="application/xhtml+xml"/>',
    ]
    manifest.extend(
        f'<item id="formula-{formula_id}" href="images/formulas/{formula_id}.png" media-type="image/png"/>'
        for formula_id in sorted(set(FORMULA_IMAGE_IDS.values()))
    )
    manifest.extend(
        f'<item id="illustration-{idx:02d}" href="images/illustrations/{illustration.name}" media-type="image/png"/>'
        for idx, illustration in enumerate(sorted((OUT_DIR / "illustrations").glob("*.png")), 1)
    )
    spine = ['<itemref idref="cover"/>', '<itemref idref="title"/>', '<itemref idref="epigraph"/>']
    for idx, section in enumerate(sections, 1):
        item_id = f"s{idx:02d}"
        manifest.append(f'<item id="{item_id}" href="text/{section.filename}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{item_id}"/>')

    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{LANG}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">urn:uuid:{uuid4()}</dc:identifier>
<dc:title>{TITLE}</dc:title><dc:creator>{AUTHOR}</dc:creator><dc:language>{LANG}</dc:language>
<meta property="dcterms:modified">{modified}</meta><meta name="cover" content="cover-image"/>
</metadata>
<manifest>{"".join(manifest)}</manifest>
<spine>{"".join(spine)}</spine>
</package>
"""
    (BUILD_DIR / "OEBPS" / "content.opf").write_text(opf, encoding="utf-8")

    if OUT_EPUB.exists():
        OUT_EPUB.unlink()
    with zipfile.ZipFile(OUT_EPUB, "w") as archive:
        archive.write(BUILD_DIR / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(BUILD_DIR.rglob("*")):
            if path.is_file() and path.name != "mimetype":
                archive.write(path, path.relative_to(BUILD_DIR), compress_type=zipfile.ZIP_DEFLATED)
    print(f"generated: {OUT_EPUB}")
    print(f"toc: {len(volumes)} volumes, {len(chapters)} chapters")


if __name__ == "__main__":
    build()

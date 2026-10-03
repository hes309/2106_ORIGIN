#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "2156_ORIGIN_手稿 copy.md"
OUT = ROOT / "ebook_output"
COVER_SRC = Path("/Users/beibei/.codex/generated_images/019e53f9-e404-7f52-aa14-80d2f8b4600f/ig_012f0126cb36ad4b016a11b840cc708191a21e7baa0f8e5146.png")

BOOK_TITLE = "2106：ORIGIN"
SUBTITLE = "起源"
AUTHOR = "何帅"
LANG = "zh-CN"


@dataclass
class Section:
    kind: str
    title: str
    filename: str
    paragraphs: list[str] = field(default_factory=list)


def strip_title_marks(text: str) -> str:
    text = text.strip()
    text = text.replace("：《", "：").replace("》", "")
    text = text.replace("《", "").replace("》", "")
    text = text.replace("，", "、", 1) if re.match(r"^[一二三四五六七八九十]+，", text) else text
    return text


def normalize_body_lines(lines: list[str]) -> list[Section]:
    start = next(i for i, line in enumerate(lines) if line.startswith("# 第一章：世界运行良好"))
    body = lines[start:]

    sections: list[Section] = []
    current: Section | None = None
    volume_index = 1
    chapter_index = 0

    def add_section(kind: str, title: str) -> Section:
        nonlocal volume_index, chapter_index
        if kind == "volume":
            filename = f"volume_{volume_index:02d}.xhtml"
            volume_index += 1
            chapter_index = 0
        else:
            chapter_index += 1
            filename = f"chapter_{volume_index - 1:02d}_{chapter_index:02d}.xhtml"
        sec = Section(kind=kind, title=strip_title_marks(title), filename=filename)
        sections.append(sec)
        return sec

    current = add_section("volume", "第一卷：黑色一分钟")

    for raw in body:
        line = raw.rstrip()
        if line == "# 《2106：ORIGIN》":
            continue
        if line.strip() == "---":
            if current and current.paragraphs and current.paragraphs[-1] != "":
                current.paragraphs.append("")
            continue

        m_volume = re.match(r"^##\s+(第[一二三四五六]卷：.+|终章：.+)$", line)
        if m_volume:
            current = add_section("volume", m_volume.group(1))
            continue

        m_first_chapter = re.match(r"^#\s+(第[一二三四五六七八九十]+章：.+)$", line)
        if m_first_chapter:
            current = add_section("chapter", m_first_chapter.group(1))
            continue

        m_chapter = re.match(r"^###\s+(.+)$", line)
        if m_chapter:
            current = add_section("chapter", m_chapter.group(1))
            continue

        m_time = re.match(r"^##\s+(\d{2}:\d{2}:\d{2})$", line)
        if m_time:
            if current:
                current.paragraphs.append(f"#### {m_time.group(1)}")
            continue

        if current is None:
            continue
        current.paragraphs.append(line)

    return [section for section in sections if section.kind == "volume" or any(p.strip() for p in section.paragraphs)]


def paragraph_to_html(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if text.startswith("#### "):
        return f"<h4>{html.escape(text[5:])}</h4>"
    if text.startswith(">"):
        return f"<blockquote>{html.escape(text.lstrip('> ').strip())}</blockquote>"
    if re.match(r"^\[[A-Z0-9_.:/ -]+\]", text) or text.startswith("[WARNING]"):
        return f"<pre>{html.escape(text)}</pre>"
    return f"<p>{html.escape(text)}</p>"


def section_xhtml(section: Section) -> str:
    body_parts: list[str] = [f"<h1>{html.escape(section.title)}</h1>"]
    for paragraph in section.paragraphs:
        item = paragraph_to_html(paragraph)
        if item:
            body_parts.append(item)
    return XHTML_TEMPLATE.format(title=html.escape(section.title), body="\n".join(body_parts))


def nav_xhtml(sections: list[Section]) -> str:
    items = []
    for sec in sections:
        cls = "volume" if sec.kind == "volume" else "chapter"
        items.append(f'<li class="{cls}"><a href="{sec.filename}">{html.escape(sec.title)}</a></li>')
    return XHTML_TEMPLATE.format(
        title="目录",
        body="<h1>目录</h1>\n<nav epub:type=\"toc\"><ol>\n" + "\n".join(items) + "\n</ol></nav>",
    )


def ncx_xml(sections: list[Section]) -> str:
    nav_points = [
        """    <navPoint id="navPoint-title" playOrder="1">
      <navLabel><text>封面</text></navLabel>
      <content src="cover.xhtml"/>
    </navPoint>""",
        """    <navPoint id="navPoint-toc" playOrder="2">
      <navLabel><text>目录</text></navLabel>
      <content src="nav.xhtml"/>
    </navPoint>""",
    ]
    order = 3
    for idx, section in enumerate(sections, start=1):
        nav_points.append(
            f"""    <navPoint id="navPoint-{idx:03d}" playOrder="{order}">
      <navLabel><text>{html.escape(section.title)}</text></navLabel>
      <content src="{section.filename}"/>
    </navPoint>"""
        )
        order += 1
    return NCX_TEMPLATE.format(title=html.escape(BOOK_TITLE), author=html.escape(AUTHOR), navpoints="\n".join(nav_points))


def title_xhtml() -> str:
    body = f"""
<section class="title-page">
  <h1>{BOOK_TITLE}</h1>
  <p class="subtitle">{SUBTITLE}</p>
  <p class="author">{AUTHOR}</p>
</section>
"""
    return XHTML_TEMPLATE.format(title=BOOK_TITLE, body=body)


def cover_xhtml() -> str:
    body = """
<section class="cover-page">
  <img src="images/cover.png" alt="2106：ORIGIN 封面"/>
</section>
"""
    return XHTML_TEMPLATE.format(title="封面", body=body)


def plain_text(sections: list[Section]) -> str:
    parts = [BOOK_TITLE, f"作者：{AUTHOR}", ""]
    for sec in sections:
        parts.append(sec.title)
        parts.append("")
        for paragraph in sec.paragraphs:
            text = paragraph.strip()
            if not text:
                continue
            if text.startswith("#### "):
                text = text[5:]
            parts.append(text)
            parts.append("")
        parts.append("")
    return "\n".join(parts).replace("\n\n\n", "\n\n")


XHTML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
{body}
</body>
</html>
"""


CSS = """
html {
  -webkit-writing-mode: horizontal-tb;
  writing-mode: horizontal-tb;
}
body {
  font-family: "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC", serif;
  line-height: 1.78;
  margin: 0 5%;
  color: #111;
}
h1 {
  font-size: 1.45em;
  line-height: 1.35;
  text-align: center;
  margin: 2.6em 0 1.8em;
  font-weight: 700;
}
h4 {
  font-size: 1em;
  text-align: center;
  margin: 1.8em 0 1em;
  font-weight: 600;
}
p {
  margin: 0.65em 0;
  text-indent: 2em;
}
blockquote {
  margin: 1em 1.2em;
  padding-left: 0.8em;
  border-left: 0.18em solid #888;
  font-family: "Songti SC", "Noto Serif CJK SC", serif;
  line-height: 1.7;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
  font-size: 0.82em;
  line-height: 1.55;
  margin: 1em 0;
  padding: 0.7em 0.8em;
  background: #f3f3f3;
  border-radius: 0.2em;
}
ol {
  list-style-type: none;
  padding-left: 0;
}
li {
  line-height: 1.75;
  margin: 0.2em 0;
}
li.chapter {
  margin-left: 1.5em;
}
a {
  color: inherit;
  text-decoration: none;
}
.title-page {
  text-align: center;
  margin-top: 35%;
}
.cover-page {
  margin: 0;
  padding: 0;
  text-align: center;
}
.cover-page img {
  max-width: 100%;
  max-height: 100vh;
  height: auto;
}
.title-page h1 {
  font-size: 2em;
  margin-bottom: 1em;
}
.subtitle,
.author {
  text-indent: 0;
  text-align: center;
  margin: 0.7em 0;
}
"""


def write_epub(sections: list[Section], epub_path: Path) -> None:
    build = OUT / "_epub_build"
    if build.exists():
        shutil.rmtree(build)
    (build / "META-INF").mkdir(parents=True)
    (build / "OEBPS").mkdir(parents=True)
    (build / "OEBPS" / "images").mkdir(parents=True)

    (build / "mimetype").write_text("application/epub+zip", encoding="utf-8")
    (build / "META-INF" / "container.xml").write_text(CONTAINER_XML, encoding="utf-8")
    (build / "OEBPS" / "style.css").write_text(CSS, encoding="utf-8")
    if not COVER_SRC.exists():
        raise FileNotFoundError(f"cover image not found: {COVER_SRC}")
    shutil.copy2(COVER_SRC, build / "OEBPS" / "images" / "cover.png")
    (build / "OEBPS" / "cover.xhtml").write_text(cover_xhtml(), encoding="utf-8")
    (build / "OEBPS" / "title.xhtml").write_text(title_xhtml(), encoding="utf-8")
    (build / "OEBPS" / "nav.xhtml").write_text(nav_xhtml(sections), encoding="utf-8")
    (build / "OEBPS" / "toc.ncx").write_text(ncx_xml(sections), encoding="utf-8")

    for section in sections:
        (build / "OEBPS" / section.filename).write_text(section_xhtml(section), encoding="utf-8")

    uid = f"urn:uuid:{uuid4()}"
    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
        '<item id="cover-image" href="images/cover.png" media-type="image/png" properties="cover-image"/>',
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
    ]
    spine_items = ['<itemref idref="cover"/>', '<itemref idref="title"/>', '<itemref idref="nav"/>']
    for idx, section in enumerate(sections, start=1):
        item_id = f"s{idx:03d}"
        manifest_items.append(f'<item id="{item_id}" href="{section.filename}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="{item_id}"/>')

    opf = OPF_TEMPLATE.format(
        uid=uid,
        title=html.escape(BOOK_TITLE),
        author=html.escape(AUTHOR),
        lang=LANG,
        manifest="\n    ".join(manifest_items),
        spine="\n    ".join(spine_items),
    )
    (build / "OEBPS" / "content.opf").write_text(opf, encoding="utf-8")

    if epub_path.exists():
        epub_path.unlink()
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.write(build / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted((build / "META-INF").rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(build), compress_type=zipfile.ZIP_DEFLATED)
        for path in sorted((build / "OEBPS").rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(build), compress_type=zipfile.ZIP_DEFLATED)


CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


OPF_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{uid}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{lang}</dc:language>
    <meta name="cover" content="cover-image"/>
    <meta property="dcterms:modified">2026-05-23T00:00:00Z</meta>
  </metadata>
  <manifest>
    {manifest}
  </manifest>
  <spine toc="ncx">
    {spine}
  </spine>
</package>
"""


NCX_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{title}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{title}</text></docTitle>
  <docAuthor><text>{author}</text></docAuthor>
  <navMap>
{navpoints}
  </navMap>
</ncx>
"""


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sections = normalize_body_lines(SRC.read_text(encoding="utf-8").splitlines())
    cleaned_md = OUT / "2106_ORIGIN_电子书排版版.md"
    cleaned_txt = OUT / "2106_ORIGIN_微信读书版.txt"
    epub_path = OUT / "2106_ORIGIN_微信读书版.epub"

    md_parts = [f"# {BOOK_TITLE}", "", f"作者：{AUTHOR}", ""]
    for section in sections:
        marker = "##" if section.kind == "volume" else "###"
        md_parts.append(f"{marker} {section.title}")
        md_parts.append("")
        for paragraph in section.paragraphs:
            text = paragraph.strip()
            if text:
                md_parts.append(text)
                md_parts.append("")
    cleaned_md.write_text("\n".join(md_parts), encoding="utf-8")
    cleaned_txt.write_text(plain_text(sections), encoding="utf-8")
    write_epub(sections, epub_path)

    print(f"sections={len(sections)}")
    print(cleaned_md)
    print(cleaned_txt)
    print(epub_path)


if __name__ == "__main__":
    main()

from pathlib import Path
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "2156_ORIGIN_手稿 copy.md"
OUT = ROOT / "2106_ORIGIN_Word友好版.docx"


def set_run_font(run, size=None, bold=None, color=None, name="宋体"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def set_style_font(style, name, size, bold=False, color=None):
    style.font.name = name
    style._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    style.font.size = Pt(size)
    style.font.bold = bold
    if color is not None:
        style.font.color.rgb = RGBColor(*color)


def add_field(paragraph, instr):
    run = paragraph.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "begin")
    run._r.append(fld_char)

    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = instr
    run._r.append(instr_text)

    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "separate")
    run._r.append(fld_char)

    run = paragraph.add_run("右键更新域以生成目录")
    set_run_font(run, 10, color=(110, 110, 110))

    run = paragraph.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char)


def configure_document(doc):
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.7)
    section.right_margin = Cm(2.7)

    styles = doc.styles
    normal = styles["Normal"]
    set_style_font(normal, "宋体", 11)
    normal.paragraph_format.first_line_indent = Pt(22)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    set_style_font(styles["Title"], "黑体", 22, bold=True)
    styles["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles["Title"].paragraph_format.space_after = Pt(12)

    set_style_font(styles["Heading 1"], "黑体", 16, bold=True, color=(0, 0, 0))
    styles["Heading 1"].paragraph_format.first_line_indent = Pt(0)
    styles["Heading 1"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles["Heading 1"].paragraph_format.space_before = Pt(18)
    styles["Heading 1"].paragraph_format.space_after = Pt(10)

    set_style_font(styles["Heading 2"], "黑体", 14, bold=True, color=(0, 0, 0))
    styles["Heading 2"].paragraph_format.first_line_indent = Pt(0)
    styles["Heading 2"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles["Heading 2"].paragraph_format.space_before = Pt(16)
    styles["Heading 2"].paragraph_format.space_after = Pt(8)

    set_style_font(styles["Heading 3"], "黑体", 12, bold=True, color=(0, 0, 0))
    styles["Heading 3"].paragraph_format.first_line_indent = Pt(0)
    styles["Heading 3"].paragraph_format.space_before = Pt(10)
    styles["Heading 3"].paragraph_format.space_after = Pt(6)

    quote = styles.add_style("Origin Quote", 1)
    set_style_font(quote, "等线", 10.5)
    quote.paragraph_format.first_line_indent = Pt(0)
    quote.paragraph_format.left_indent = Cm(0.75)
    quote.paragraph_format.right_indent = Cm(0.35)
    quote.paragraph_format.line_spacing = 1.25
    quote.paragraph_format.space_before = Pt(3)
    quote.paragraph_format.space_after = Pt(3)

    meta = styles.add_style("Origin Metadata", 1)
    set_style_font(meta, "宋体", 10.5)
    meta.paragraph_format.first_line_indent = Pt(0)
    meta.paragraph_format.space_after = Pt(2)

    toc = styles.add_style("Origin TOC Line", 1)
    set_style_font(toc, "宋体", 10.5)
    toc.paragraph_format.first_line_indent = Pt(0)
    toc.paragraph_format.left_indent = Cm(0.5)
    toc.paragraph_format.space_after = Pt(1)

    sep = styles.add_style("Origin Separator", 1)
    set_style_font(sep, "宋体", 10)
    sep.paragraph_format.first_line_indent = Pt(0)
    sep.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sep.paragraph_format.space_before = Pt(6)
    sep.paragraph_format.space_after = Pt(6)

    scene = styles.add_style("Origin Scene Heading", 1)
    set_style_font(scene, "黑体", 11, bold=True)
    scene.paragraph_format.first_line_indent = Pt(0)
    scene.paragraph_format.space_before = Pt(8)
    scene.paragraph_format.space_after = Pt(4)


def paragraph(doc, text, style="Normal", align=None, first_line=True):
    p = doc.add_paragraph(style=style)
    if not first_line:
        p.paragraph_format.first_line_indent = Pt(0)
    if align is not None:
        p.alignment = align
    if text:
        run = p.add_run(text)
        if style == "Normal":
            set_run_font(run, 11)
        elif style == "Origin Quote":
            set_run_font(run, 10.5, name="等线")
        elif style in ("Origin Metadata", "Origin TOC Line", "Origin Separator"):
            set_run_font(run, 10.5)
    return p


def main():
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines()
    toc_body_marker = "\n---\n\n## 第一卷：黑色一分钟"
    body_start_char = text.index(toc_body_marker) + len("\n---\n\n")
    body_start_line = text[:body_start_char].count("\n")

    doc = Document()
    configure_document(doc)

    in_toc = False
    in_body = False
    added_toc_field = False
    last_was_heading = False

    for idx, raw in enumerate(lines):
        line = raw.rstrip()
        stripped = line.strip()
        if idx == body_start_line:
            in_toc = False
            in_body = True

        if not stripped:
            continue

        if stripped == "---":
            if in_toc:
                doc.add_page_break()
                continue
            paragraph(doc, "＊ ＊ ＊", style="Origin Separator", align=WD_ALIGN_PARAGRAPH.CENTER, first_line=False)
            last_was_heading = False
            continue

        if stripped == "# 目录":
            in_toc = True
            p = paragraph(doc, "目录", style="Heading 1", first_line=False)
            p.paragraph_format.page_break_before = False
            hint = paragraph(doc, "以下为手稿目录；Word 导航窗格以正文卷章标题为准。", style="Origin Metadata", first_line=False)
            hint.alignment = WD_ALIGN_PARAGRAPH.CENTER
            field_p = doc.add_paragraph()
            field_p.paragraph_format.first_line_indent = Pt(0)
            add_field(field_p, r'TOC \\o "1-2" \\h \\z \\u')
            added_toc_field = True
            continue

        if in_toc:
            if re.match(r"^## (第一卷|第二卷|第三卷|终章)：", stripped):
                paragraph(doc, stripped[3:], style="Origin TOC Line", first_line=False)
                continue
            if re.match(r"^第[一二三四五六七八九十百零]+章：", stripped):
                paragraph(doc, stripped, style="Origin TOC Line", first_line=False)
                continue
            if stripped.startswith("## 作品信息"):
                paragraph(doc, "作品信息", style="Heading 1", first_line=False)
                continue

        if stripped == "## 第一卷：黑色一分钟" and in_body:
            paragraph(doc, "第一卷：黑色一分钟", style="Heading 1", first_line=False)
            last_was_heading = True
            continue

        if stripped.startswith("# 《"):
            paragraph(doc, stripped[2:], style="Title", first_line=False)
            continue

        if stripped.startswith("- "):
            paragraph(doc, stripped[2:], style="Origin Metadata", first_line=False)
            continue

        m_volume = re.match(r"^## (第一卷|第二卷|第三卷|终章)：(.+)$", stripped)
        if m_volume:
            p = paragraph(doc, f"{m_volume.group(1)}：{m_volume.group(2)}", style="Heading 1", first_line=False)
            p.paragraph_format.page_break_before = True
            last_was_heading = True
            continue

        m_chapter = re.match(r"^#{1,3} (第[一二三四五六七八九十百零]+章：.+)$", stripped)
        if m_chapter:
            p = paragraph(doc, m_chapter.group(1), style="Heading 2", first_line=False)
            p.paragraph_format.keep_with_next = True
            last_was_heading = True
            continue

        if stripped.startswith(">"):
            q = stripped.lstrip(">").strip()
            paragraph(doc, q, style="Origin Quote", first_line=False)
            last_was_heading = False
            continue

        if stripped.startswith("## "):
            paragraph(doc, stripped[3:], style="Origin Scene Heading", first_line=False)
            last_was_heading = True
            continue

        paragraph(doc, stripped, style="Normal", first_line=True)
        last_was_heading = False

    doc.core_properties.title = "2106：起源"
    doc.core_properties.author = "何帅"
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()

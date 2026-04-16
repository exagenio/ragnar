import json
import base64
import struct
from io import BytesIO
from tempfile import NamedTemporaryFile

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import plotly.io as pio


def generate_report_document(report, sections):
    """Generate report document"""
    doc = Document()

    _add_title_page(doc, report)
    doc.add_page_break()

    _add_table_of_contents(doc, sections)
    doc.add_page_break()

    for section_num, section in enumerate(sections, start=1):
        _add_section(doc, section, report, section_num)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer


def _add_title_page(doc, report):
    """Add title page"""
    title = doc.add_heading(report.title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = title.runs[0]
    run.font.size = Pt(32)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 51, 102)


def _add_table_of_contents(doc, sections):
    """Add table of contents"""

    heading = doc.add_heading("Table of Contents", level=1)
    heading.runs[0].font.color.rgb = RGBColor(0, 51, 102)

    doc.add_paragraph()

    for section_num, section in enumerate(sections, start=1):
        section_para = doc.add_paragraph()
        run = section_para.add_run(f"• {section.title}")
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0, 51, 102)

        for subsection_num, subsection in enumerate(section.sub_sections.all(), start=1):
            sub_para = doc.add_paragraph()
            sub_para.paragraph_format.left_indent = Inches(0.3)
            run = sub_para.add_run(f"◦ {subsection.title}")
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(51, 102, 153)

            for topic_num, topic in enumerate(subsection.topics.filter(is_approved=True), start=1):
                topic_para = doc.add_paragraph()
                topic_para.paragraph_format.left_indent = Inches(0.6)
                topic_number = f"{section_num}.{subsection_num}.{topic_num}"
                run = topic_para.add_run(f"{topic_number} {topic.title}")
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(102, 153, 204)

        doc.add_paragraph()


def _add_section(doc, section, report, section_num):
    """Add section"""

    heading = doc.add_heading(f"{section_num}. {section.title}", level=1)
    run = heading.runs[0]

    style_heading(run, 1)
    run.font.color.rgb = RGBColor(0, 51, 102)

    if hasattr(section, 'content') and section.content.status == 'generated':
        _add_section_content(doc, section.content.content_json)

    for subsection_num, subsection in enumerate(section.sub_sections.all(), start=1):
        _add_subsection(doc, subsection, report, section_num, subsection_num)

    doc.add_page_break()


def _add_section_content(doc, content_json):
    """Add section content"""

    if 'section_introduction' in content_json:
        for text in content_json['section_introduction'].get('paragraphs', []):
            para = doc.add_paragraph(text)
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def _add_subsection(doc, subsection, report, section_num, subsection_num):
    """Add subsection"""

    heading = doc.add_heading(f"{section_num}.{subsection_num} {subsection.title}", level=2)
    run = heading.runs[0]

    style_heading(run, 2)
    run.font.color.rgb = RGBColor(51, 102, 153)

    if hasattr(subsection, 'content') and subsection.content.status == 'generated':
        _add_subsection_content(doc, subsection.content.content_json)

    for topic_num, topic in enumerate(subsection.topics.filter(is_approved=True), start=1):
        _add_topic(doc, topic, section_num, subsection_num, topic_num)


def _add_subsection_content(doc, content_json):
    """Add subsection content"""

    if 'subsection_introduction' in content_json:
        for text in content_json['subsection_introduction'].get('paragraphs', []):
            para = doc.add_paragraph(text)
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def _add_topic(doc, topic, section_num, subsection_num, topic_num):
    """Add topic"""

    heading = doc.add_heading(f"{section_num}.{subsection_num}.{topic_num} {topic.title}", level=3)
    run = heading.runs[0]

    style_heading(run, 3)
    run.font.color.rgb = RGBColor(102, 153, 204)

    if hasattr(topic, 'content') and topic.content.status == 'generated':
        _add_topic_content(doc, topic.content.content_json)


def _add_topic_content(doc, content_json):
    """Add topic content"""

    for section in content_json.get('sections', []):
        for block in section.get('content_blocks', []):
            _add_content_block(doc, block)


def _add_content_block(doc, block):
    """Add content block"""

    # Handle different content block types
    block_type = block.get('type')

    if block_type == 'paragraph':
        para = doc.add_paragraph(block.get('content', ''))
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    elif block_type == 'bullet_list':
        for item in block.get('content', []):
            doc.add_paragraph(item, style='List Bullet')

    elif block_type == 'visual_placeholder':
        _add_visual(doc, block)


def _add_visual(doc, block):
    """Add visual"""

    # Render plotly figures or tables
    visual = block.get("generated_visual", {})

    if visual.get("status") != "ok":
        return

    fig_json = visual.get("figure_json")

    if not fig_json:
        return

    if visual.get("visual_spec", {}).get("type") == "table":
        _render_table(doc, visual)
        return

    try:
        fig = pio.from_json(fig_json)
        tmp = NamedTemporaryFile(delete=False, suffix=".png")
        fig.write_image(tmp.name)

        doc.add_picture(tmp.name, width=Inches(6))
    except Exception:
        pass


def _render_table(doc, visual):
    """Render table"""

    # Build table from plotly json
    try:
        fig = json.loads(visual.get("figure_json"))
    except Exception:
        return

    data = fig.get("data", [])
    if not data:
        return

    table_data = data[0]

    headers = table_data.get("header", {}).get("values", [])
    cells = table_data.get("cells", {}).get("values", [])

    if not headers or not cells:
        return

    table = doc.add_table(rows=len(cells[0]) + 1, cols=len(headers))

    for i, header in enumerate(headers):
        table.rows[0].cells[i].text = str(header)

    for row_idx in range(len(cells[0])):
        for col_idx in range(len(headers)):
            table.rows[row_idx + 1].cells[col_idx].text = str(cells[col_idx][row_idx])


def decode_bdata(bdata, dtype):
    """Decode binary data"""

    binary = base64.b64decode(bdata)

    if dtype == "f8":
        return list(struct.unpack(f"{len(binary)//8}d", binary))
    if dtype == "f4":
        return list(struct.unpack(f"{len(binary)//4}f", binary))
    if dtype == "i4":
        return list(struct.unpack(f"{len(binary)//4}i", binary))
    if dtype == "i2":
        return list(struct.unpack(f"{len(binary)//2}h", binary))
    if dtype == "i1":
        return list(struct.unpack(f"{len(binary)}b", binary))

    return []


def style_heading(run, level):
    """Style heading"""

    if level == 1:
        run.font.size = Pt(18)
        run.font.bold = True

    elif level == 2:
        run.font.size = Pt(14)
        run.font.bold = True

    elif level == 3:
        run.font.size = Pt(12)
        run.font.bold = True

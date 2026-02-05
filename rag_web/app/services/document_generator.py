from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import os
from django.conf import settings


def generate_report_document(report, sections):
    """
    Generate a Word document from the report with hierarchical content.

    Document Structure:
    - Report Title Page
    - Report Purpose
    - Sections (Level 1)
      - Section Content (if available)
      - SubSections (Level 2)
        - SubSection Content (if available)
        - Topics (Level 3)
          - Topic Content (if available)

    Args:
        report: Report model instance
        sections: QuerySet of Section objects with prefetched relations

    Returns:
        BytesIO: Document buffer ready for download
    """

    doc = Document()

    # ============================================
    # TITLE PAGE
    # ============================================
    _add_title_page(doc, report)
    doc.add_page_break()

    # ============================================
    # TABLE OF CONTENTS
    # ============================================
    _add_table_of_contents(doc, sections)
    doc.add_page_break()

    # ============================================
    # MAIN CONTENT - HIERARCHICAL STRUCTURE
    # ============================================
    for section_num, section in enumerate(sections, start=1):
        _add_section(doc, section, report, section_num)

    # Save to buffer
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer


def _add_title_page(doc, report):
    """Add report title page - title only."""

    # Main title
    title = doc.add_heading(report.title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.runs[0]
    title_run.font.size = Pt(32)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0, 51, 102)


def _add_table_of_contents(doc, sections):
    """Add table of contents with sections, subsections, and topics."""

    # Table of Contents heading
    toc_heading = doc.add_heading("Table of Contents", level=1)
    toc_heading_run = toc_heading.runs[0]
    toc_heading_run.font.color.rgb = RGBColor(0, 51, 102)

    doc.add_paragraph()

    # Iterate through sections
    for section_num, section in enumerate(sections, start=1):
        # Section (Level 1)
        section_para = doc.add_paragraph()
        section_run = section_para.add_run(f"• {section.title}")
        section_run.font.size = Pt(12)
        section_run.font.bold = True
        section_run.font.color.rgb = RGBColor(0, 51, 102)
        section_para.paragraph_format.space_after = Pt(6)

        # Subsections (Level 2)
        subsections = section.sub_sections.all()
        for subsection_num, subsection in enumerate(subsections, start=1):
            subsection_para = doc.add_paragraph()
            subsection_para.paragraph_format.left_indent = Inches(0.3)
            subsection_run = subsection_para.add_run(f"◦ {subsection.title}")
            subsection_run.font.size = Pt(11)
            subsection_run.font.color.rgb = RGBColor(51, 102, 153)
            subsection_para.paragraph_format.space_after = Pt(4)

            # Topics (Level 3) with numbering
            topics = subsection.topics.filter(is_approved=True)
            for topic_num, topic in enumerate(topics, start=1):
                topic_number = f"{section_num}.{subsection_num}.{topic_num}"
                topic_para = doc.add_paragraph()
                topic_para.paragraph_format.left_indent = Inches(0.6)
                topic_run = topic_para.add_run(f"{topic_number} {topic.title}")
                topic_run.font.size = Pt(10)
                topic_run.font.color.rgb = RGBColor(102, 153, 204)
                topic_para.paragraph_format.space_after = Pt(2)

        # Add spacing after each section
        doc.add_paragraph()


def _add_section(doc, section, report, section_num):
    """Add a complete section with all its subsections and topics."""

    # Section heading (Level 1)
    section_heading = doc.add_heading(section.title, level=1)
    section_heading_run = section_heading.runs[0]
    section_heading_run.font.color.rgb = RGBColor(0, 51, 102)

    # Add section content if available
    if hasattr(section, 'content') and section.content.status == 'generated':
        _add_section_content(doc, section.content.content_json)

    # Add all subsections
    subsections = section.sub_sections.all()
    for subsection_num, subsection in enumerate(subsections, start=1):
        _add_subsection(doc, subsection, report, section_num, subsection_num)

    # Page break after each section
    doc.add_page_break()


def _add_section_content(doc, content_json):
    """Add section-level content (introduction and strategic insights)."""

    # Section introduction
    if 'section_introduction' in content_json:
        intro = content_json['section_introduction']
        if 'paragraphs' in intro:
            for paragraph_text in intro['paragraphs']:
                para = doc.add_paragraph(paragraph_text)
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                para.paragraph_format.space_after = Pt(12)

    # Strategic insights
    if 'strategic_insights' in content_json and content_json['strategic_insights']:
        doc.add_heading("Strategic Insights", level=2)
        for insight in content_json['strategic_insights']:
            para = doc.add_paragraph(insight, style='List Bullet')
            para.paragraph_format.left_indent = Inches(0.5)


def _add_subsection(doc, subsection, report, section_num, subsection_num):
    """Add a complete subsection with all its topics."""

    # SubSection heading (Level 2)
    subsection_heading = doc.add_heading(subsection.title, level=2)
    subsection_heading_run = subsection_heading.runs[0]
    subsection_heading_run.font.color.rgb = RGBColor(51, 102, 153)

    # Add subsection content if available
    if hasattr(subsection, 'content') and subsection.content.status == 'generated':
        _add_subsection_content(doc, subsection.content.content_json)

    # Add all topics with numbering
    topics = subsection.topics.filter(is_approved=True)
    for topic_num, topic in enumerate(topics, start=1):
        _add_topic(doc, topic, section_num, subsection_num, topic_num)


def _add_subsection_content(doc, content_json):
    """Add subsection-level content (introduction and key themes)."""

    # Subsection introduction
    if 'subsection_introduction' in content_json:
        intro = content_json['subsection_introduction']
        if 'paragraphs' in intro:
            for paragraph_text in intro['paragraphs']:
                para = doc.add_paragraph(paragraph_text)
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                para.paragraph_format.space_after = Pt(12)

    # Key themes
    if 'key_themes' in content_json and content_json['key_themes']:
        doc.add_heading("Key Themes", level=3)
        for theme in content_json['key_themes']:
            para = doc.add_paragraph(theme, style='List Bullet')
            para.paragraph_format.left_indent = Inches(0.5)


def _add_topic(doc, topic, section_num, subsection_num, topic_num):
    """Add a complete topic with all its content."""

    # Topic heading (Level 3) with numbering
    topic_number = f"{section_num}.{subsection_num}.{topic_num}"
    topic_heading = doc.add_heading(f"{topic_number} {topic.title}", level=3)
    topic_heading_run = topic_heading.runs[0]
    topic_heading_run.font.color.rgb = RGBColor(102, 153, 204)

    # Add topic content if available
    if hasattr(topic, 'content') and topic.content.status == 'generated':
        _add_topic_content(doc, topic.content.content_json)


def _add_topic_content(doc, content_json):
    """Add topic-level detailed content."""

    # Content sections
    if 'sections' in content_json:
        for content_section in content_json['sections']:

            # Section heading (Level 4)
            if 'heading' in content_section and content_section['heading']:
                doc.add_heading(content_section['heading'], level=4)

            # Content blocks
            if 'content_blocks' in content_section:
                for block in content_section['content_blocks']:
                    _add_content_block(doc, block)


def _add_content_block(doc, block):
    """Add individual content blocks (paragraphs, lists, SQL results, visuals)."""

    block_type = block.get('type', '')

    if block_type == 'paragraph':
        content = block.get('content', '')
        para = doc.add_paragraph(content)
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        para.paragraph_format.space_after = Pt(12)

    elif block_type == 'bullet_list':
        items = block.get('content', [])
        for item in items:
            para = doc.add_paragraph(item, style='List Bullet')
            para.paragraph_format.left_indent = Inches(0.5)

    elif block_type == 'sql_placeholder':
        _add_sql_result(doc, block)

    elif block_type == 'visual_placeholder':
        _add_visual(doc, block)


def _add_sql_result(doc, block):
    """Add SQL analysis results or placeholder."""

    generated_result = block.get('generated_result', {})

    if generated_result.get('status') == 'ok':
        interpretation = generated_result.get('interpretation', {})

        # Analysis title
        if 'title' in interpretation:
            doc.add_heading(interpretation['title'], level=5)

        # Interpretation paragraphs
        if 'paragraphs' in interpretation:
            for paragraph in interpretation['paragraphs']:
                para = doc.add_paragraph(paragraph)
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                para.paragraph_format.space_after = Pt(12)

        # Key findings
        if 'key_findings' in interpretation:
            doc.add_heading("Key Findings", level=5)
            for finding in interpretation['key_findings']:
                para = doc.add_paragraph(finding, style='List Bullet')
                para.paragraph_format.left_indent = Inches(0.5)
    else:
        # SQL not computed
        placeholder_text = block.get('content', '[SQL Analysis Pending]')
        para = doc.add_paragraph(f"⚠ Analysis Pending: {placeholder_text}")
        para.style = 'Intense Quote'
        para.paragraph_format.space_after = Pt(12)


def _add_visual(doc, block):
    """Add visual/chart or placeholder."""

    generated_visual = block.get('generated_visual', {})

    if generated_visual.get('status') == 'ok':
        image_path = generated_visual.get('image_path', '')
        if image_path:
            try:
                # Convert relative path to absolute path
                if image_path.startswith('/media/'):
                    # Remove /media/ prefix and join with MEDIA_ROOT
                    relative_path = image_path.replace('/media/', '', 1)
                    absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)
                else:
                    # Use path as-is if it's already absolute
                    absolute_path = image_path

                # Check if file exists before adding
                if os.path.exists(absolute_path):
                    doc.add_picture(absolute_path, width=Inches(6))
                    last_paragraph = doc.paragraphs[-1]
                    last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    last_paragraph.paragraph_format.space_after = Pt(12)
                else:
                    # Skip if image doesn't exist (don't show error message)
                    pass
            except Exception:
                # Skip if image can't be loaded (don't show error message)
                pass
    else:
        # Visual not generated - skip without showing message
        pass

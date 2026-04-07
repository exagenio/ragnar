import textstat
from app.models import TopicContent, TopicReadability
from app.services.evaluation_service import extract_content_blocks_text


def compute_fk_grade(text: str) -> float:

    if not text or not text.strip():
        return 0.0

    return textstat.flesch_kincaid_grade(text)


def evaluate_topic_readability(topic, report):

    content_obj = TopicContent.objects.filter(topic=topic).first()
    if not content_obj:
        return None

    content_json = content_obj.content_json or {}

    # 🔥 reuse your existing logic
    text = extract_content_blocks_text(content_json)

    fk_score = compute_fk_grade(text)

    TopicReadability.objects.update_or_create(
        topic=topic,
        report=report,
        defaults={
            "flesch_kincaid_grade": fk_score
        },
    )

    return fk_score

from app.models import Topic, Report


def evaluate_project_readability(project_id, report_id):

    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    for topic in topics:
        evaluate_topic_readability(topic, report)
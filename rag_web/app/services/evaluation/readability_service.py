import textstat
from app.models import TopicContent, TopicReadability, Topic, Report


def extract_readable_text(content_json):

    sections = content_json.get("sections", [])
    texts = []

    for section in sections:
        blocks = section.get("content_blocks", [])

        for block in blocks:

            block_type = block.get("type")

            if block_type == "paragraph":
                text = block.get("content") or block.get("text", "")
                if text:
                    texts.append(str(text))

            elif block_type == "bullet_list":
                items = block.get("content") or block.get("items", [])
                if isinstance(items, str):
                    items = [items]
                for item in items:
                    if item:
                        texts.append(str(item))

    return "\n".join(texts).strip()


def compute_fk_grade(text: str) -> float:

    if not text or not text.strip():
        return 0.0

    try:
        return round(textstat.flesch_kincaid_grade(text), 2)
    except Exception as e:
        print(f"[READABILITY ERROR] FK failed: {str(e)}")
        return 0.0


def evaluate_topic_readability(topic, report):

    content_obj = TopicContent.objects.filter(topic=topic).first()

    if not content_obj:
        print(f"[READABILITY SKIP] Topic {topic.id} - no content")
        return None

    content_json = content_obj.content_json or {}

    text = extract_readable_text(content_json)

    if not text:
        print(f"[READABILITY SKIP] Topic {topic.id} - empty text")
        return None

    fk_score = compute_fk_grade(text)

    TopicReadability.objects.update_or_create(
        topic=topic,
        report=report,
        defaults={
            "flesch_kincaid_grade": fk_score
        },
    )

    print(f"[READABILITY DONE] Topic {topic.id} → FK: {fk_score}")

    return fk_score


def evaluate_project_readability(project_id, report_id):

    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    print(f"[READABILITY START] Report {report_id} → {topics.count()} topics")

    processed = 0
    skipped = 0

    for topic in topics:

        result = evaluate_topic_readability(topic, report)

        if result is None:
            skipped += 1
        else:
            processed += 1

    print(
        f"[READABILITY COMPLETE] Processed: {processed}, Skipped: {skipped}"
    )

    return {
        "processed": processed,
        "skipped": skipped,
        "total": topics.count(),
    }

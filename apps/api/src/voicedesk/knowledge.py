"""Curated, source-attributed synthetic business policies."""

import json
from functools import lru_cache

from voicedesk.config import get_settings


@lru_cache
def articles() -> list[dict]:
    path = get_settings().api_root / "fixtures" / "knowledge_base.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["articles"]


def scoped_articles(workspace_id: str) -> list[dict]:
    return articles() if workspace_id in {"cedar-demo", "cedar-connected"} else []


def answer_policy(question: str, service_id: str | None, workspace_id: str) -> str:
    available = scoped_articles(workspace_id)
    if not available:
        return "I do not have a verified policy source for that request. I can hand it to an operator."
    query = question.lower()
    selected = next((article for article in available if article.get("service_id") == service_id), None)
    if not selected:
        selected = next((article for article in available if article["title"].lower() in query), None)
    if not selected and any(word in query for word in ["cancel", "book", "reschedule"]):
        selected = next((article for article in available if article["id"] == "booking-policy"), None)
    if not selected and any(word in query for word in ["zone", "travel", "area"]):
        selected = next((article for article in available if article["id"] == "service-zones"), None)
    if not selected:
        return "Which service or policy should I look up? I can give only sourced information from Cedar's curated policy."
    return f"{selected['body']} Source: {selected['source']}."

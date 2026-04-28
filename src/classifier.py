"""Deduplication and classification pipeline.

Merges identical items across sources, assigns sections and tags,
and flags major vs. routine content.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from src.models import ClassifiedItem, ScrapedItem

logger = logging.getLogger(__name__)


def make_dedup_key(item: ScrapedItem) -> str:
    raw = f"{item.source}:{item.title}:{item.url or ''}"
    return hashlib.md5(raw.encode()).hexdigest()


SECTION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("city-hall", ["city council", "planning commission", "architectural review",
                    "city manager", "budget", "ordinance", "resolution", "city clerk",
                    "state of the city", "public hearing", "zoning", "city meeting"]),
    ("public-safety", ["police", "fire", "emergency", "crime", "safety", "alert",
                       "evacuation", "law enforcement", "traffic"]),
    ("schools", ["school", "pgusd", "board of education", "student", "teacher",
                 "district", "classroom", "education", "pg high", "middle school",
                 "elementary", "forest grove", "robert h down"]),
    ("library-culture", ["library", "museum", "heritage", "art", "music",
                         "concert", "exhibit", "author", "book"]),
    ("community-calendar", ["event", "meeting", "workshop", "farmers market",
                            "volunteer", "recreation", "park", "festival"]),
]

URGENCY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("emergency", ["evacuation", "boil water", "shelter in place", "emergency",
                   "hazard", "warning", "alert monterey"]),
    ("time-sensitive", ["deadline", "closes", "register", "apply", "comment period",
                        "tonight", "tomorrow", "this week", "due"]),
]


def classify(items: list[ScrapedItem]) -> list[ClassifiedItem]:
    classified = []
    seen_dedup: set[str] = set()

    for item in items:
        key = make_dedup_key(item)
        if key in seen_dedup:
            continue
        seen_dedup.add(key)

        title_lower = (item.title or "").lower()
        body_lower = (item.body_text or item.excerpt or "").lower()
        combined = f"{title_lower} {body_lower}"

        # Section classification
        section = item.category or "community-calendar"
        for sec, keywords in SECTION_KEYWORDS:
            if any(kw in combined for kw in keywords):
                section = sec
                break

        # Urgency classification
        urgency = "routine"
        for urg, keywords in URGENCY_KEYWORDS:
            if any(kw in combined for kw in keywords):
                urgency = urg
                break

        # Major flag
        major_keywords = ["budget", "policy change", "election", "measure",
                          "ordinance", "bond", "levy", "appointment", "layoff",
                          "investigation", "lawsuit", "settlement"]
        is_major = any(kw in combined for kw in major_keywords)

        tags = _derive_tags(section, urgency, item)

        classified.append(ClassifiedItem(
            scraped=item,
            tags=tags,
            section=section,
            urgency=urgency,
            is_major=is_major,
            dedup_key=key,
        ))

    logger.info(f"Classified {len(classified)} items ({len(items)} raw, {len(items) - len(classified)} duplicates removed)")
    return classified


def _derive_tags(section: str, urgency: str, item: ScrapedItem) -> list[str]:
    from src.config import GHOST_TAGS_BY_SECTION, GHOST_TAGS_BY_URGENCY
    tags = []
    if section in GHOST_TAGS_BY_SECTION:
        tags.append(GHOST_TAGS_BY_SECTION[section])
    if urgency in GHOST_TAGS_BY_URGENCY:
        tags.append(GHOST_TAGS_BY_URGENCY[urgency])
    tags.append("Grover Daily")

    if item.category == "meeting":
        tags.append("Meeting")
    elif item.category == "event":
        tags.append("Event")
    elif item.category == "police":
        tags.append("Police")

    return tags

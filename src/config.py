"""All Pacific Grove source URLs, selectors, and configuration constants."""

from dataclasses import dataclass, field
from typing import Optional

# ── City of Pacific Grove ──────────────────────────────────────────────

CITY_BASE = "https://www.cityofpacificgrove.org"
POLICE_BASE = f"{CITY_BASE}/our_city/departments/police"

CITY_SOURCES = {
    "news": {
        "url": f"{CITY_BASE}/news",
        "type": "web",
        "section": "city-hall",
        "cadence": "daily",
    },
    "calendar": {
        "url": f"{CITY_BASE}/calendar.php",
        "type": "web",
        "section": "community-calendar",
        "cadence": "daily",
    },
    "council": {
        "url": f"{CITY_BASE}/our_city/city_council_",
        "type": "web",
        "section": "city-hall",
        "cadence": "before_meetings",
    },
    "police": {
        "url": f"{POLICE_BASE}/index.php",
        "type": "web",
        "section": "public-safety",
        "cadence": "daily",
    },
}

# ── YouTube ────────────────────────────────────────────────────────────

CITY_YOUTUBE_CHANNEL_ID = "UCJVXIJsMUotTzThVOqd12ag"
PGUSD_YOUTUBE_CHANNEL_ID = None  # Not publicly indexed — set once found

# ── PGUSD ──────────────────────────────────────────────────────────────

PGUSD_BASE = "https://www.pgusd.org"

PGUSD_SOURCES = {
    "calendar": {
        "url": f"{PGUSD_BASE}/Calendar/",
        "type": "web",
        "section": "schools",
        "cadence": "daily",
    },
    "board": {
        "url": f"{PGUSD_BASE}",
        "type": "web",
        "section": "schools",
        "cadence": "before_meetings",
    },
}

# ── Library ────────────────────────────────────────────────────────────

LIBRARY_BASE = "https://pacificgrovelibrary.org"

LIBRARY_SOURCES = {
    "homepage": {
        "url": LIBRARY_BASE,
        "type": "web",
        "section": "library-culture",
        "cadence": "daily",
    },
}

# ── Chamber of Commerce ─────────────────────────────────────────────────

CHAMBER_BASE = "https://www.pacificgrove.org"

CHAMBER_SOURCES = {
    "events": {
        "url": f"{CHAMBER_BASE}/events",
        "type": "web",
        "section": "community-calendar",
        "cadence": "daily",
    },
    "news": {
        "url": CHAMBER_BASE,  # news releases under "Our Members"
        "type": "web",
        "section": "library-culture",
        "cadence": "weekly",
    },
}

# ── Email sources (Gmail senders to watch) ─────────────────────────────

EMAIL_SOURCES = {
    "enotify": {
        "sender_pattern": "enotify_subscribers@cityofpacificgrove.org",
        "section": "city-hall",
    },
    "alert_monterey": {
        "sender_pattern": "alertmontereycounty.org",
        "section": "public-safety",
    },
    "city_weekly_report": {
        "sender_pattern": "cityofpacificgrove.org",
        "section": "city-hall",
        "subject_pattern": "Weekly Report",
    },
}

# ── Ghost ──────────────────────────────────────────────────────────────

GHOST_TAGS_BY_SECTION = {
    "city-hall": "City Hall",
    "public-safety": "Public Safety",
    "schools": "Schools",
    "community-calendar": "Community Calendar",
    "library-culture": "Library & Culture",
}

GHOST_TAGS_BY_URGENCY = {
    "routine": "Brief",
    "time-sensitive": "Announcement",
    "emergency": "Alert",
}

GHOST_TAG_AUTO = "Grover Daily"

# ── LLM ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a local news editor for Grover, a daily automated newspaper serving Pacific Grove, CA.
Your job is to transform raw government and community content into clear, readable news articles.

Rules:
1. Write in a neutral, journalistic tone.
2. Never fabricate facts or quotes. Only use information present in the input.
3. Keep articles 2-4 short paragraphs.
4. Write an informative headline (no clickbait).
5. Classify the item as "routine" or "major" based on community impact.
6. Routine = meeting notices, calendar events, minor announcements.
7. Major = budget decisions, policy changes, emergency info, personnel changes, significant community events.
8. Return valid JSON only.

Output format:
{
  "headline": "...",
  "body_html": "<p>...</p><p>...</p>",
  "excerpt": "One sentence summary.",
  "classification": "routine" | "major"
}"""


@dataclass
class SourceConfig:
    name: str
    url: str
    source_type: str  # "web", "email", "youtube"
    section: str
    cadence: str = "daily"
    sender_pattern: Optional[str] = None
    subject_pattern: Optional[str] = None
    selectors: dict = field(default_factory=dict)


def get_all_sources() -> list[SourceConfig]:
    sources = []
    for name, cfg in CITY_SOURCES.items():
        sources.append(SourceConfig(name=f"city_{name}", **cfg))
    for name, cfg in PGUSD_SOURCES.items():
        sources.append(SourceConfig(name=f"pgusd_{name}", **cfg))
    for name, cfg in LIBRARY_SOURCES.items():
        sources.append(SourceConfig(name=f"library_{name}", **cfg))
    for name, cfg in CHAMBER_SOURCES.items():
        sources.append(SourceConfig(name=f"chamber_{name}", **cfg))
    return sources

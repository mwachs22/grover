from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScrapedItem:
    source: str
    source_type: str  # "web", "email", "youtube"
    title: str
    url: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    excerpt: Optional[str] = None
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    category: Optional[str] = None  # raw category from source
    raw: dict = field(default_factory=dict)


@dataclass
class ClassifiedItem:
    scraped: ScrapedItem
    tags: list[str] = field(default_factory=list)
    section: str = ""  # city-hall, public-safety, schools, community-calendar, library-culture
    urgency: str = "routine"  # routine, time-sensitive, emergency
    is_major: bool = False
    dedup_key: str = ""


@dataclass
class Story:
    classified: ClassifiedItem
    headline: str = ""
    body: str = ""  # HTML body for Ghost
    excerpt: str = ""
    ghost_url: Optional[str] = None
    ghost_id: Optional[str] = None
    published: bool = False

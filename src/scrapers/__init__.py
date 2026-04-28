"""Web scrapers for all Pacific Grove public information sources.

Each scraper function takes a Playwright page (for JS-rendered sites) or
a requests session and returns a list of ScrapedItem.
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import ScrapedItem

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Grover/0.1"
}


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


# ── City News ──────────────────────────────────────────────────────────

def scrape_city_news(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(f"{base_url}/news")
    items = []
    for article in soup.select("article, .news-item, .article, [class*=news]"):
        title_el = article.select_one("h2, h3, .title, a[href*='/news']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        date_el = article.select_one("time, .date, .published")
        pub_date = None
        if date_el:
            try:
                pub_date = datetime.fromisoformat(date_el.get_text(strip=True))
            except ValueError:
                pass

        body_el = article.select_one(".content, .body, p")
        excerpt = body_el.get_text(strip=True)[:500] if body_el else ""

        if title and len(title) > 5:
            items.append(ScrapedItem(
                source="city_news",
                source_type="web",
                title=title,
                url=link,
                body_text=excerpt,
                excerpt=excerpt,
                published_at=pub_date,
                category="news",
            ))
    return items


# ── City Calendar ──────────────────────────────────────────────────────

def scrape_city_calendar(base_url: str) -> list[ScrapedItem]:
    """Calendar page is JS-rendered (Revize CMS). Falls back to fetching any
    visible event entries. May need Playwright for completeness."""
    try:
        soup = fetch_soup(f"{base_url}/calendar.php")
    except Exception:
        logger.warning("City calendar page failed to load")
        return []

    items = []
    for event in soup.select("[class*=event], [class*=calendar-item], tr"):
        title_el = event.select_one("a, .title, strong")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        date_el = event.select_one("time, .date, .event-date, td:first-child")
        pub_date = None
        if date_el:
            try:
                pub_date = datetime.fromisoformat(date_el.get_text(strip=True))
            except ValueError:
                pass

        desc_el = event.select_one("p, .description, .body")
        excerpt = desc_el.get_text(strip=True)[:300] if desc_el else ""

        items.append(ScrapedItem(
            source="city_calendar",
            source_type="web",
            title=title,
            url=link,
            body_text=excerpt,
            excerpt=excerpt,
            published_at=pub_date,
            category="event",
        ))
    return items


# ── City Council ───────────────────────────────────────────────────────

def scrape_city_council(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(f"{base_url}/our_city/city_council_")
    items = []

    for link in soup.select("a[href$='.pdf'], a[href*='agenda'], a[href*='minutes']"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or not href:
            continue
        full_url = href if href.startswith("http") else urljoin(base_url, href)
        items.append(ScrapedItem(
            source="city_council",
            source_type="web",
            title=title,
            url=full_url,
            category="meeting",
        ))

    return items


# ── Police ─────────────────────────────────────────────────────────────

def scrape_police(base_url: str) -> list[ScrapedItem]:
    police_url = f"{base_url}/our_city/departments/police/index.php"
    soup = fetch_soup(police_url)
    items = []

    news_section = soup.select_one("#news, .news, [class*=news]")
    if not news_section:
        news_section = soup

    for article in news_section.select("article, li, .item, .news-item"):
        title_el = article.select_one("a, h2, h3, strong")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        desc_el = article.select_one("p, .description, .body")
        excerpt = desc_el.get_text(strip=True)[:300] if desc_el else ""

        if title and len(title) > 3:
            items.append(ScrapedItem(
                source="police",
                source_type="web",
                title=title,
                url=link,
                body_text=excerpt,
                excerpt=excerpt,
                category="police",
            ))

    return items


# ── PGUSD Calendar ─────────────────────────────────────────────────────

def scrape_pgusd_calendar(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(f"{base_url}/Calendar/")
    items = []

    for link in soup.select("a[href$='.pdf']"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or "calendar" not in title.lower():
            continue
        full_url = href if href.startswith("http") else urljoin(base_url, href)
        items.append(ScrapedItem(
            source="pgusd_calendar",
            source_type="web",
            title=title,
            url=full_url,
            category="calendar",
        ))

    for event in soup.select("[class*=event], .fc-event, .calendar-event"):
        title_el = event.select_one("a, .title, .fc-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)
        items.append(ScrapedItem(
            source="pgusd_calendar",
            source_type="web",
            title=title,
            url=link,
            category="event",
        ))

    return items


# ── PGUSD Board ────────────────────────────────────────────────────────

def scrape_pgusd_board(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(base_url)
    items = []

    board_links = soup.select("a[href*='Board'], a[href*='board'], a[href*='agenda']")
    for link in board_links:
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or len(title) < 5:
            continue
        full_url = href if href.startswith("http") else urljoin(base_url, href)
        items.append(ScrapedItem(
            source="pgusd_board",
            source_type="web",
            title=title,
            url=full_url,
            category="meeting",
        ))

    return items


# ── Library Homepage ───────────────────────────────────────────────────

def scrape_library(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(base_url)
    items = []

    for article in soup.select("article, .news-item, .post, [class*=news]"):
        title_el = article.select_one("h2, h3, a, .title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        desc_el = article.select_one("p, .description, .excerpt")
        excerpt = desc_el.get_text(strip=True)[:300] if desc_el else ""

        date_el = article.select_one("time, .date")
        pub_date = None
        if date_el:
            try:
                pub_date = datetime.fromisoformat(date_el.get_text(strip=True))
            except ValueError:
                pass

        if title and len(title) > 3:
            items.append(ScrapedItem(
                source="library",
                source_type="web",
                title=title,
                url=link,
                body_text=excerpt,
                excerpt=excerpt,
                published_at=pub_date,
                category="news",
            ))

    return items


# ── Chamber Events ─────────────────────────────────────────────────────

def scrape_chamber_events(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(f"{base_url}/events")
    items = []

    for event in soup.select("[class*=event], .calendar-event, .event-item, .mn-event-list-item"):
        title_el = event.select_one("a, .title, .event-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        date_el = event.select_one("time, .date, .event-date")
        pub_date = None
        if date_el:
            try:
                pub_date = datetime.fromisoformat(date_el.get_text(strip=True))
            except ValueError:
                pass

        desc_el = event.select_one("p, .description, .event-description")
        excerpt = desc_el.get_text(strip=True)[:300] if desc_el else ""

        if title and len(title) > 3:
            items.append(ScrapedItem(
                source="chamber_events",
                source_type="web",
                title=title,
                url=link,
                body_text=excerpt,
                excerpt=excerpt,
                published_at=pub_date,
                category="event",
            ))

    return items


# ── Chamber News ──────────────────────────────────────────────────────

def scrape_chamber_news(base_url: str) -> list[ScrapedItem]:
    soup = fetch_soup(base_url)
    items = []

    for section in soup.select("section, div, [class*=news]"):
        title_el = section.select_one("h2, h3, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        link = title_el.get("href") or ""
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        excerpt_el = section.select_one("p")
        excerpt = excerpt_el.get_text(strip=True)[:300] if excerpt_el else ""

        if title and "news" in title.lower() or "release" in title.lower():
            items.append(ScrapedItem(
                source="chamber_news",
                source_type="web",
                title=title,
                url=link,
                excerpt=excerpt,
                category="news",
            ))

    return items


# ── Orchestrator ────────────────────────────────────────────────────────

SCRAPER_REGISTRY = {
    "city_news": scrape_city_news,
    "city_calendar": scrape_city_calendar,
    "city_council": scrape_city_council,
    "police": scrape_police,
    "pgusd_calendar": scrape_pgusd_calendar,
    "pgusd_board": scrape_pgusd_board,
    "library": scrape_library,
    "chamber_events": scrape_chamber_events,
    "chamber_news": scrape_chamber_news,
}


def run_scrapers(base_urls: dict[str, str]) -> list[ScrapedItem]:
    all_items = []
    for name, scraper in SCRAPER_REGISTRY.items():
        base = base_urls.get(name.split("_")[0])
        if base is None:
            base = _infer_base_url(name)
        try:
            items = scraper(base)
            logger.info(f"Scraped {len(items)} items from {name}")
            all_items.extend(items)
        except Exception as e:
            logger.error(f"Scraper {name} failed: {e}")
    return all_items


def _infer_base_url(name: str) -> str:
    from src.config import CITY_BASE, PGUSD_BASE, LIBRARY_BASE, CHAMBER_BASE
    mapping = {
        "city": CITY_BASE,
        "pgusd": PGUSD_BASE,
        "library": LIBRARY_BASE,
        "chamber": CHAMBER_BASE,
    }
    for prefix, url in mapping.items():
        if name.startswith(prefix):
            return url
    return CITY_BASE

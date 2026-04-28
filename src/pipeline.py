"""Main pipeline orchestrator.

Runs all ingestion (scrapers + Gmail + YouTube), classification,
summarization, and publishing in sequence. Designed to be called
from a cron job or GitHub Action.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from src import classifier
from src.config import CITY_BASE, CITY_YOUTUBE_CHANNEL_ID, PGUSD_BASE, LIBRARY_BASE, CHAMBER_BASE
from src.models import ScrapedItem

logger = logging.getLogger(__name__)


INGESTION_SOURCES = {
    "city_news": CITY_BASE,
    "city_calendar": CITY_BASE,
    "city_council": CITY_BASE,
    "police": CITY_BASE,
    "pgusd_calendar": PGUSD_BASE,
    "pgusd_board": PGUSD_BASE,
    "library": LIBRARY_BASE,
    "chamber_events": CHAMBER_BASE,
    "chamber_news": CHAMBER_BASE,
}


def run_pipeline(
    enable_gmail: bool = True,
    enable_youtube: bool = True,
    enable_web: bool = True,
    dry_run: bool = False,
) -> dict:
    """Execute the full Grover pipeline. Returns a summary dict."""
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scraped": 0,
        "emails": 0,
        "youtube": 0,
        "classified": 0,
        "stories": 0,
        "published": 0,
        "drafted": 0,
        "errors": [],
    }
    all_items: list[ScrapedItem] = []

    # ── Stage 1: Web Scrapers ──────────────────────────────────────────
    if enable_web:
        from src.scrapers import run_scrapers
        try:
            web_items = run_scrapers(INGESTION_SOURCES)
            all_items.extend(web_items)
            summary["scraped"] = len(web_items)
            logger.info(f"Web scrapers: {len(web_items)} items")
        except Exception as e:
            logger.error(f"Web scraping failed: {e}")
            summary["errors"].append(f"web_scraping: {e}")

    # ── Stage 1b: YouTube ──────────────────────────────────────────────
    if enable_youtube:
        from src.scrapers.youtube import fetch_channel_uploads
        try:
            yt_items = fetch_channel_uploads(CITY_YOUTUBE_CHANNEL_ID)
            all_items.extend(yt_items)
            summary["youtube"] = len(yt_items)
            logger.info(f"YouTube: {len(yt_items)} items")
        except Exception as e:
            logger.error(f"YouTube fetch failed: {e}")
            summary["errors"].append(f"youtube: {e}")

    # ── Stage 1c: Gmail Reader ─────────────────────────────────────────
    if enable_gmail:
        try:
            from src.gmail_reader import GmailReader
            reader = GmailReader()
            reader.authenticate()
            email_items = reader.read_unread()
            all_items.extend(email_items)
            summary["emails"] = len(email_items)
            logger.info(f"Gmail: {len(email_items)} items")
        except Exception as e:
            logger.error(f"Gmail reader failed: {e}")
            summary["errors"].append(f"gmail: {e}")

    if not all_items:
        logger.info("No items found from any source")
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    # ── Stage 2: Classification & Dedup ─────────────────────────────────
    try:
        classified = classifier.classify(all_items)
        summary["classified"] = len(classified)
        logger.info(f"Classified: {len(classified)} items")
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        summary["errors"].append(f"classification: {e}")
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    # ── Stage 3: LLM Summarization ─────────────────────────────────────
    stories = []
    try:
        from src.summarizer import Summarizer
        summarizer = Summarizer()
        stories = summarizer.summarize_batch(classified)
        summary["stories"] = len(stories)
        logger.info(f"Summarized: {len(stories)} stories")
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        summary["errors"].append(f"summarization: {e}")
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    if not stories:
        logger.info("No stories generated")
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        return summary

    # ── Stage 4: Publish to Ghost ──────────────────────────────────────
    if not dry_run:
        try:
            from src.publisher import GhostPublisher
            publisher = GhostPublisher()
            for story in stories:
                publisher.publish(story)
                if story.published:
                    summary["published"] += 1
                elif story.ghost_id:
                    summary["drafted"] += 1
            logger.info(f"Published: {summary['published']}, Drafted: {summary['drafted']}")
        except Exception as e:
            logger.error(f"Publishing failed: {e}")
            summary["errors"].append(f"publishing: {e}")
    else:
        logger.info(f"Dry run: would publish {len(stories)} stories")
        for s in stories:
            logger.info(f"  [{s.classified.urgency}] {s.headline} | tags={s.classified.tags}")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"Pipeline complete: {summary}")
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    dry_run = "--dry-run" in sys.argv
    summary = run_pipeline(dry_run=dry_run)
    print(f"\nPipeline summary: {json.dumps(summary, indent=2, default=str)}")

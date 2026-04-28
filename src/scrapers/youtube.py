"""YouTube API reader for public meeting recordings.

Fetches recent uploads from known Pacific Grove YouTube channels
and returns them as ScrapedItems for the pipeline.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from src.models import ScrapedItem

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
PLAYLIST_ITEM_MAX = 10


def fetch_channel_uploads(channel_id: str, api_key: Optional[str] = None) -> list[ScrapedItem]:
    api_key = api_key or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.warning("No YOUTUBE_API_KEY set, skipping YouTube")
        return []
    if not channel_id:
        logger.warning("No channel_id provided, skipping YouTube")
        return []

    try:
        uploads_id = _get_uploads_playlist_id(channel_id, api_key)
        if not uploads_id:
            return []
        return _get_playlist_items(uploads_id, api_key, channel_id)
    except Exception as e:
        logger.error(f"YouTube fetch failed for channel {channel_id}: {e}")
        return []


def _get_uploads_playlist_id(channel_id: str, api_key: str) -> Optional[str]:
    resp = requests.get(
        f"{YOUTUBE_API_BASE}/channels",
        params={"part": "contentDetails", "id": channel_id, "key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _get_playlist_items(playlist_id: str, api_key: str, channel_id: str) -> list[ScrapedItem]:
    resp = requests.get(
        f"{YOUTUBE_API_BASE}/playlistItems",
        params={
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": PLAYLIST_ITEM_MAX,
            "key": api_key,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        published = snippet.get("publishedAt", "")
        if published:
            try:
                pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                pub_date = None
        else:
            pub_date = None

        if pub_date and pub_date < cutoff:
            continue

        title = snippet.get("title", "")
        description = snippet.get("description", "")
        video_id = snippet.get("resourceId", {}).get("videoId", "")
        video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        thumbnails = snippet.get("thumbnails", {})
        thumb = thumbnails.get("high", thumbnails.get("medium", thumbnails.get("default", {}))).get("url")

        if not title:
            continue

        items.append(ScrapedItem(
            source=f"youtube:{channel_id}",
            source_type="youtube",
            title=title,
            url=video_url,
            body_text=description,
            excerpt=description[:300],
            published_at=pub_date,
            image_url=thumb,
            category="meeting",
        ))

    return items

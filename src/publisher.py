"""Ghost Admin API publisher.

Creates posts in Ghost via the Admin API. Handles deduplication
by checking for existing posts with matching titles. Includes rate
limiting to avoid overwhelming the Ghost instance.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

import requests

from src.models import Story

logger = logging.getLogger(__name__)


class GhostPublisher:
    def __init__(self, api_url: Optional[str] = None, admin_api_key: Optional[str] = None):
        self.api_url = (api_url or os.getenv("GHOST_API_URL", "")).rstrip("/")
        self.admin_api_key = admin_api_key or os.getenv("GHOST_ADMIN_API_KEY", "")
        if not self.api_url or not self.admin_api_key:
            raise ValueError("GHOST_API_URL and GHOST_ADMIN_API_KEY must be set")
        self._existing_posts_cache = None

    def _token(self) -> str:
        id_, secret_part = self.admin_api_key.split(":")
        try:
            secret_bytes = bytes.fromhex(secret_part)
        except ValueError:
            secret_bytes = base64.b64decode(secret_part)
        iat = int(time.time())
        header = {
            "alg": "HS256",
            "kid": id_,
            "typ": "JWT",
        }
        body = {
            "iat": iat,
            "exp": iat + 5 * 60,
            "aud": "/admin/",
        }

        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        body_b64 = base64.urlsafe_b64encode(json.dumps(body).encode()).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(
            hmac.new(secret_bytes, f"{header_b64}.{body_b64}".encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()

        return f"{header_b64}.{body_b64}.{sig}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Ghost {self._token()}",
            "Content-Type": "application/json",
            "Accept-Version": "v5.0",
        }

    def _load_existing(self):
        if self._existing_posts_cache is not None:
            return self._existing_posts_cache
        url = f"{self.api_url}/ghost/api/admin/posts/"
        params = {"filter": "tag:Grover Daily", "limit": "200"}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code != 200:
            self._existing_posts_cache = {}
            return self._existing_posts_cache
        cache = {}
        for post in resp.json().get("posts", []):
            meta = post.get("codeinjection_head", "") or ""
            cache[meta] = post["id"]
            cache[post.get("title", "")] = post["id"]
        self._existing_posts_cache = cache
        return cache

    def publish(self, story: Story) -> Optional[str]:
        body_html = self._build_body(story)
        status = "draft" if story.classified.is_major else "published"

        logger.info(f"SENDING '{story.headline}': body_html len={len(body_html)}")
        if len(body_html.strip()) < 20:
            logger.warning(f"BODY_TOO_SHORT (len={len(body_html)}): {body_html}")

        data = {
            "posts": [{
                "title": story.headline,
                "html": body_html,
                "excerpt": story.excerpt[:300],
                "status": status,
                "tags": [{"name": t} for t in story.classified.tags],
                "meta_title": story.headline[:70],
                "meta_description": story.excerpt[:160],
                "codeinjection_head": (
                    f'<meta name="grover-source-url" content="{story.classified.scraped.url or ""}">\n'
                    f'<meta name="grover-source" content="{story.classified.scraped.source}">'
                ),
            }]
        }

        existing_id = None
        existing_cache = self._load_existing()
        url_meta = f'content="{story.classified.scraped.url or ""}"'
        title = story.classified.scraped.title
        for key, pid in existing_cache.items():
            if url_meta in key or (title and title == key):
                existing_id = pid
                break

        if existing_id:
            resp = requests.put(
                f"{self.api_url}/ghost/api/admin/posts/{existing_id}/",
                headers=self._headers(),
                json=data,
                timeout=30,
            )
        else:
            resp = requests.post(
                f"{self.api_url}/ghost/api/admin/posts/",
                headers=self._headers(),
                json=data,
                timeout=30,
            )

            if resp.status_code == 429:
                logger.warning("Rate limited, waiting 5s...")
                time.sleep(5)
                resp = requests.post(
                    f"{self.api_url}/ghost/api/admin/posts/",
                    headers=self._headers(),
                    json=data,
                    timeout=30,
                )

        if resp.status_code in (200, 201):
            result = resp.json()["posts"][0]
            story.ghost_id = result["id"]
            story.ghost_url = result.get("url")
            story.published = status == "published"
            verb = "Updated" if existing_id else ("Published" if story.published else "Drafted")
            logger.info(f"{verb}: {story.headline} (id={result['id']})")
            return result["id"]
        else:
            logger.error(f"Ghost API error ({resp.status_code}): {resp.text[:500]}")
            return None

    def publish_batch(self, stories: list[Story]) -> list[Story]:
        for story in stories:
            self.publish(story)
        return stories

    def _build_body(self, story: Story) -> str:
        parts = [story.body]
        scraped = story.classified.scraped
        if scraped.url:
            parts.append(f'<p class="source-link">Source: <a href="{scraped.url}">{scraped.url}</a></p>')
        return "\n".join(parts)

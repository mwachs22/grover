"""Ghost Admin API publisher.

Creates posts in Ghost via the Admin API. Handles deduplication
by checking for existing posts with matching source URLs.
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

    def _token(self) -> str:
        id_, secret_b64 = self.admin_api_key.split(":")
        secret_bytes = base64.b64decode(secret_b64)

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

    def post_exists(self, source_url: str) -> Optional[str]:
        url = f"{self.api_url}/ghost/api/admin/posts/"
        params = {"filter": f"tag:Grover Daily", "limit": "50"}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code != 200:
            return None
        for post in resp.json().get("posts", []):
            meta_url = post.get("codeinjection_head", "") or ""
            if source_url in meta_url:
                logger.info(f"Post already exists: {post.get('title')} (id={post.get('id')})")
                return post.get("id")
        return None

    def publish(self, story: Story) -> Optional[str]:
        if story.classified.scraped.url:
            existing_id = self.post_exists(story.classified.scraped.url)
            if existing_id:
                story.ghost_id = existing_id
                story.published = True
                return existing_id

        body_html = self._build_body(story)
        status = "draft" if story.classified.is_major else "published"

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
            logger.info(f"{'Published' if story.published else 'Drafted'}: {story.headline} (id={result['id']})")
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

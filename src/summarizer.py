"""Claude-powered summarizer that transforms raw content into newspaper stories.

Calls Anthropic API with a structured prompt to generate headlines,
HTML body, excerpt, and classification.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urljoin

import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup

from src.config import SYSTEM_PROMPT
from src.models import ClassifiedItem, ScrapedItem, Story

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = Anthropic(api_key=self.api_key)
        self.model = model

    def summarize(self, item: ClassifiedItem) -> Optional[Story]:
        content = self._build_prompt(item.scraped)
        if not content:
            return None

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.3,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            result = self._parse_response(response)
            if not result:
                return None
        except Exception as e:
            logger.error(f"LLM call failed for '{item.scraped.title}': {e}")
            return None

        return Story(
            classified=item,
            headline=result.get("headline", item.scraped.title),
            body=result.get("body_html", f"<p>{item.scraped.excerpt or ''}</p>"),
            excerpt=result.get("excerpt", item.scraped.excerpt or ""),
        )

    def _fetch_url_text(self, url: str) -> Optional[str]:
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Grover/0.1"
            })
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text[:3000]
        except Exception as e:
            logger.debug(f"Failed to fetch URL {url}: {e}")
            return None

    def summarize_batch(self, items: list[ClassifiedItem], max_workers: int = 5) -> list[Story]:
        stories = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = pool.map(self.summarize, items)
            for r in results:
                if r:
                    stories.append(r)
        logger.info(f"Generated {len(stories)} stories from {len(items)} items")
        return stories

    def _build_prompt(self, item: ScrapedItem) -> str:
        parts = [f"Title: {item.title}"]
        if item.url:
            parts.append(f"URL: {item.url}")
        if item.body_text:
            parts.append(f"Body:\n{item.body_text[:3000]}")
        elif item.excerpt:
            parts.append(f"Excerpt:\n{item.excerpt}")
        elif item.url:
            fetched = self._fetch_url_text(item.url)
            if fetched:
                parts.append(f"Page content:\n{fetched}")
        if item.published_at:
            parts.append(f"Date: {item.published_at.isoformat()}")
        return "\n\n".join(parts)

    def _parse_response(self, response) -> Optional[dict]:
        try:
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None

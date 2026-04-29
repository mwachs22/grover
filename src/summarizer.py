"""LLM-powered summarizer that transforms raw content into newspaper stories.

Uses OpenAI-compatible API (Ollama, DeepSeek, etc.) to generate headlines,
HTML body, excerpt, and classification. Configure via OLLAMA_API_KEY and
OLLAMA_BASE_URL environment variables.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

from src.config import SYSTEM_PROMPT
from src.models import ClassifiedItem, ScrapedItem, Story

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://ollama.com/v1"


class Summarizer:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL
        if not self.api_key:
            raise ValueError("OLLAMA_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def summarize(self, item: ClassifiedItem) -> Optional[Story]:
        content = self._build_prompt(item.scraped)
        if not content:
            return None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
            )
            result_text = response.choices[0].message.content or ""
            result = self._parse_response(result_text)
            if not result:
                logger.warning(f"Parse fail for '{item.scraped.title}'. Raw: {result_text[:400]}")
                return None
        except Exception as e:
            logger.error(f"LLM call failed for '{item.scraped.title}': {e}")
            return None

        body = result.get("body_html") or result.get("html") or result.get("body") or ""
        if not body.strip():
            body = f"<p>{item.scraped.excerpt or item.scraped.body_text or ''}</p>"
            logger.warning(f"No body content. Keys: {list(result.keys())}, first 200 chars of response: {json.dumps(result)[:200]}")

        if not result.get("headline") and not result.get("title"):
            logger.warning(f"Empty headline. Keys: {list(result.keys())}, raw: {json.dumps(result)[:200]}")

        return Story(
            classified=item,
            headline=result.get("headline", item.scraped.title),
            body=body,
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

    def _parse_response(self, text: str) -> Optional[dict]:
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None

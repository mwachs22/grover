"""Gmail inbox reader for email-only newsletter sources.

Authenticates via Google service account (domain-wide delegation) or OAuth2.
Queries unread messages from known senders, parses body, marks as read.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import EMAIL_SOURCES
from src.models import ScrapedItem

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.modify"]


class GmailReader:
    def __init__(self, user_id: str = "me"):
        self.user_id = user_id
        self.service = None

    def authenticate(self, service_account_json_path: Optional[str] = None):
        if service_account_json_path and os.path.exists(service_account_json_path):
            with open(service_account_json_path) as f:
                info = json.load(f)
            creds = ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)
            self.service = build("gmail", "v1", credentials=creds)
            logger.info("Authenticated via service account")
            return

        env_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if env_json:
            try:
                info = json.loads(env_json)
                creds = ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)
                self.service = build("gmail", "v1", credentials=creds)
                logger.info("Authenticated via service account from env var")
                return
            except json.JSONDecodeError:
                logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON env var is not valid JSON, falling back to OAuth")

        creds = None
        token_file = "credentials/token.json"
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                os.makedirs("credentials", exist_ok=True)
                with open(token_file, "w") as f:
                    f.write(creds.to_json())
            else:
                client_secret_file = "credentials/client_secret.json"
                if os.path.exists(client_secret_file):
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secret_file, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    os.makedirs("credentials", exist_ok=True)
                    with open(token_file, "w") as f:
                        f.write(creds.to_json())
                else:
                    logger.warning("No Gmail credentials found (no client_secret.json, no token.json). Skipping Gmail.")
                    self.service = None
                    return

        if creds:
            self.service = build("gmail", "v1", credentials=creds)
            logger.info("Authenticated via OAuth")

    def read_unread(self, max_results: int = 50) -> list[ScrapedItem]:
        if not self.service:
            raise RuntimeError("GmailReader not authenticated. Call authenticate() first.")

        items = []
        all_senders = [cfg["sender_pattern"] for cfg in EMAIL_SOURCES.values()]

        for sender in all_senders:
            query = f"from:({sender}) is:unread"
            try:
                results = (
                    self.service.users()
                    .messages()
                    .list(userId=self.user_id, q=query, maxResults=max_results)
                    .execute()
                )
                messages = results.get("messages", [])
            except HttpError as e:
                logger.error(f"Gmail API error for query '{query}': {e}")
                continue

            for msg in messages:
                item = self._process_message(msg["id"], sender)
                if item:
                    items.append(item)

        return items

    def _process_message(self, msg_id: str, sender_pattern: str) -> Optional[ScrapedItem]:
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=msg_id, format="full")
                .execute()
            )
        except HttpError as e:
            logger.error(f"Failed to fetch message {msg_id}: {e}")
            return None

        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        from_header = headers.get("from", "")
        date_str = headers.get("date", "")

        # Determine section from sender pattern
        section = self._match_section(sender_pattern)

        # Extract body (prefer plain text)
        body_text, body_html = self._extract_body(msg["payload"])
        body = body_text or body_html or ""

        # Remove excessive whitespace
        if body_text:
            body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()

        published_at = self._parse_date(date_str)

        item = ScrapedItem(
            source=f"email:{sender_pattern}",
            source_type="email",
            title=subject,
            url=None,
            body_html=body_html,
            body_text=body_text,
            excerpt=body_text[:200] if body_text else "",
            published_at=published_at,
            category="email",
            raw={"message_id": msg_id, "from": from_header, "sender": sender_pattern},
        )

        # Mark as read
        try:
            self.service.users().messages().modify(
                userId=self.user_id, id=msg_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except HttpError:
            pass

        return item

    def _extract_body(self, payload: dict) -> tuple[Optional[str], Optional[str]]:
        body_text = None
        body_html = None

        if "parts" in payload:
            for part in payload["parts"]:
                mime = part.get("mimeType", "")
                if mime == "text/plain" and part.get("body", {}).get("data"):
                    import base64
                    decoded = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    body_text = decoded
                elif mime == "text/html" and part.get("body", {}).get("data"):
                    import base64
                    decoded = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    body_html = decoded
                else:
                    # Recurse into nested parts
                    bt, bh = self._extract_body(part)
                    body_text = body_text or bt
                    body_html = body_html or bh
                    if body_text and body_html:
                        break
        elif payload.get("body", {}).get("data"):
            import base64
            decoded = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            mime = payload.get("mimeType", "")
            if mime == "text/html":
                body_html = decoded
            else:
                body_text = decoded

        return body_text, body_html

    def _match_section(self, sender: str) -> str:
        for name, cfg in EMAIL_SOURCES.items():
            if cfg["sender_pattern"] in sender:
                return cfg["section"]
        return "city-hall"

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now(timezone.utc)

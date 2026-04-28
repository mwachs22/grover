"""Debug script to test Ghost Admin API authentication.

Run: python -m src.test_ghost
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import time

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GHOST_API_URL = os.getenv("GHOST_API_URL", "").rstrip("/")
GHOST_ADMIN_API_KEY = os.getenv("GHOST_ADMIN_API_KEY", "")


def _token() -> str:
    id_, secret_b64 = GHOST_ADMIN_API_KEY.split(":")
    secret_bytes = base64.b64decode(secret_b64)
    iat = int(time.time())
    header_b64 = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "kid": id_, "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body_b64 = base64.urlsafe_b64encode(
        json.dumps({"iat": iat, "exp": iat + 5 * 60, "aud": "/admin/"}).encode()
    ).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(secret_bytes, f"{header_b64}.{body_b64}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header_b64}.{body_b64}.{sig}"


def main():
    logger.info(f"GHOST_API_URL: {GHOST_API_URL}")
    logger.info(f"Key format: {GHOST_ADMIN_API_KEY.count(':')} colon(s)")

    id_part, secret_part = GHOST_ADMIN_API_KEY.split(":")
    logger.info(f"Key ID: {id_part}")
    logger.info(f"Secret part length: {len(secret_part)}")

    # Try decoding as base64
    try:
        decoded = base64.b64decode(secret_part)
        logger.info(f"b64 decoded: {len(decoded)} bytes")
    except Exception as e:
        logger.error(f"b64 decode failed: {e}")

    # Try decoding as urlsafe base64
    try:
        decoded = base64.urlsafe_b64decode(secret_part + "==")
        logger.info(f"b64 urlsafe decoded: {len(decoded)} bytes")
    except Exception as e:
        logger.error(f"b64 urlsafe decode failed: {e}")

    # Test token
    token = _token()
    logger.info(f"Token: {token[:100]}...")

    # Test request
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
        "Accept-Version": "v5.0",
    }
    resp = requests.get(f"{GHOST_API_URL}/ghost/api/admin/posts/", headers=headers, timeout=10)
    logger.info(f"Response: HTTP {resp.status_code}")
    logger.info(f"Body: {resp.text[:500]}")


if __name__ == "__main__":
    main()

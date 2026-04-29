"""Debug script to test Ghost Admin API authentication.

Tests multiple JWT signing approaches against the live Ghost API.
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


def make_token(id_: str, secret_bytes: bytes) -> str:
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


def test_auth(label: str, id_: str, secret_bytes: bytes):
    token = make_token(id_, secret_bytes)
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
        "Accept-Version": "v5.0",
    }
    try:
        resp = requests.get(f"{GHOST_API_URL}/ghost/api/admin/posts/", headers=headers, timeout=10)
        logger.info(f"  [{label}] HTTP {resp.status_code} (secret: {len(secret_bytes)} bytes)")
        if resp.status_code == 200:
            logger.info(f"  *** THIS APPROACH WORKS ***")
            return True
    except Exception as e:
        logger.error(f"  [{label}] Error: {e}")
    return False


def main():
    logger.info(f"Ghost URL: {GHOST_API_URL}")

    # Verify URL is reachable at all
    try:
        r = requests.get(f"{GHOST_API_URL}/ghost/api/admin/posts/", timeout=10,
                         headers={"Accept-Version": "v5.0"})
        logger.info(f"Unauthenticated GET: HTTP {r.status_code}")
    except Exception as e:
        logger.error(f"Cannot reach Ghost URL: {e}")
        return

    id_part, secret_part = GHOST_ADMIN_API_KEY.split(":")
    logger.info(f"Key ID: {id_part}")
    logger.info(f"Secret string length: {len(secret_part)}")
    logger.info(f"Secret string: {secret_part[:20]}...{secret_part[-20:]}")

    # Approach 1: base64 decode (standard)
    try:
        s1 = base64.b64decode(secret_part)
        logger.info(f"Approach 1 - b64decode: {len(s1)} bytes")
        test_auth("b64decode", id_part, s1)
    except Exception as e:
        logger.error(f"  b64decode failed: {e}")

    # Approach 2: base64 urlsafe decode
    try:
        padding = 4 - len(secret_part) % 4
        if padding != 4:
            s2 = base64.urlsafe_b64decode(secret_part + "=" * padding)
        else:
            s2 = base64.urlsafe_b64decode(secret_part)
        logger.info(f"Approach 2 - urlsafe: {len(s2)} bytes")
        test_auth("urlsafe", id_part, s2)
    except Exception as e:
        logger.error(f"  urlsafe decode failed: {e}")

    # Approach 3: hex decode (32 bytes)
    try:
        s3 = bytes.fromhex(secret_part)
        logger.info(f"Approach 3 - hex: {len(s3)} bytes")
        test_auth("hex", id_part, s3)
    except Exception as e:
        logger.error(f"  hex decode failed: {e}")

    # Approach 4: use raw string (no decode)
    test_auth("raw_string", id_part, secret_part.encode("utf-8"))

    # Approach 5: Ghost v5 uses standard base64 without padding, decode with b64decode
    try:
        import base64 as b64mod
        s5 = b64mod.b64decode(secret_part)
        logger.info(f"Approach 5 - stdlib b64: {len(s5)} bytes")
        test_auth("stdlib_b64", id_part, s5)
    except Exception as e:
        logger.error(f"  stdlib b64 failed: {e}")


if __name__ == "__main__":
    main()

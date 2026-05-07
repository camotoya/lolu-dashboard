"""Cliente Shopify minimalista para el dashboard.

Maneja Client Credentials Grant + paginación cursor (Link header).
Cachea el token en data/.shopify_token.json para no re-solicitar cada hora.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

TOKEN_CACHE = ROOT / "data" / ".shopify_token.json"


class ShopifyClient:
    def __init__(self):
        self.store = os.environ["SHOPIFY_STORE"]
        self.client_id = os.environ["SHOPIFY_CLIENT_ID"]
        self.client_secret = os.environ["SHOPIFY_CLIENT_SECRET"]
        self.api_version = os.environ.get("SHOPIFY_API_VERSION", "2025-10")
        self.base = f"https://{self.store}/admin/api/{self.api_version}"
        self._token: str | None = None

    def _load_cached(self) -> str | None:
        if not TOKEN_CACHE.exists():
            return None
        try:
            d = json.loads(TOKEN_CACHE.read_text())
            if d.get("store") != self.store:
                return None
            exp = datetime.fromisoformat(d["expires_at"])
            if exp > datetime.now(timezone.utc) + timedelta(minutes=5):
                return d["access_token"]
        except Exception:
            pass
        return None

    def _save(self, token: str, expires_in: int) -> None:
        TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE.write_text(json.dumps({
            "store": self.store,
            "access_token": token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        }, indent=2))

    def token(self) -> str:
        if self._token:
            return self._token
        c = self._load_cached()
        if c:
            self._token = c
            return c
        r = requests.post(
            f"https://{self.store}/admin/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._save(self._token, body.get("expires_in", 86399))
        return self._token

    def _headers(self):
        return {"X-Shopify-Access-Token": self.token()}

    def fetch_all(self, resource: str, **params) -> list[dict]:
        items: list[dict] = []
        params.setdefault("limit", 250)
        url = f"{self.base}/{resource}.json"
        first = True
        while url:
            for attempt in range(3):
                r = requests.get(url, headers=self._headers(),
                                 params=params if first else None, timeout=30)
                if r.status_code == 429:
                    time.sleep(float(r.headers.get("Retry-After", "2")))
                    continue
                break
            r.raise_for_status()
            data = r.json()
            key = resource.split("/")[-1]
            items.extend(data.get(key, []))
            url = self._next_url(r.headers.get("Link", ""))
            first = False
            time.sleep(0.3)
        return items

    @staticmethod
    def _next_url(link_header: str) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            m = re.match(r'\s*<([^>]+)>\s*;\s*rel="next"', part)
            if m:
                return m.group(1)
        return None

"""Pull orders de Shopify y agruparlos para el dashboard v2.

Output: data/current/shopify.json con shape:
{
  "totals_by_period": {
    "day":   {"current": {orders, revenue, aov}, "prev": {...}},
    "week":  {...},
    "month": {...}
  },
  "timeseries": {
    "daily_18":   [{date, orders, revenue}],
    "weekly_18":  [{week_start, orders, revenue}],
    "monthly_18": [{month, orders, revenue}]
  },
  "breakdown_channel_mtd": [...],
  "breakdown_city_mtd":    [...],
  "top_products_mtd":      [...]
}
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from _shopify import ShopifyClient
from _periods import periods_today, last_n_days, last_n_weeks, last_n_months, bogota_today

ROOT = Path(__file__).parent.parent
TZ_OFFSET = "-05:00"

# Cuántos días hacia atrás necesitamos pullear para llenar las 3 series
# 18 meses ≈ 540 días. Usamos 560 para margen.
PULL_DAYS = 560


def parse_utms(landing: str) -> dict[str, str]:
    if not landing:
        return {}
    qs = parse_qs(urlparse(landing).query)
    return {k: (qs.get(k, [""])[0] or "") for k in
            ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")}


def classify_channel(o: dict) -> str:
    landing = o.get("landing_site", "") or ""
    qs = parse_qs(urlparse(landing).query) if landing else {}
    utms = parse_utms(landing)
    src = (utms.get("utm_source") or "").lower()
    med = (utms.get("utm_medium") or "").lower()
    if src == "meta" and med == "paid_social":
        return "meta_paid"
    if qs.get("fbclid") or "fbclid=" in landing:
        return "meta_paid"
    if src in ("ig", "instagram"):
        return "ig_organic"
    if src in ("fb", "facebook"):
        return "fb_organic"
    if src == "google" or qs.get("gclid"):
        return "google_organic" if (med in ("organic", "") and not qs.get("gclid")) else "google_paid"
    if src == "email" or med == "email":
        return "email"
    if src == "whatsapp" or "whatsapp" in (o.get("referring_site", "") or "").lower():
        return "whatsapp"
    if not src and not (o.get("referring_site") or "").strip():
        return "direct"
    return "other"


def order_revenue(o: dict) -> float:
    return float(o.get("total_price", 0) or 0)


CITY_NORMALIZATIONS = {
    "bogota": "Bogotá", "bogotá": "Bogotá", "santa fe de bogota": "Bogotá",
    "santafé de bogotá": "Bogotá", "bogota d.c.": "Bogotá", "bogota dc": "Bogotá",
    "medellin": "Medellín", "medellín": "Medellín",
    "cali": "Cali", "barranquilla": "Barranquilla", "bucaramanga": "Bucaramanga",
    "cartagena": "Cartagena", "cartagena de indias": "Cartagena",
    "manizales": "Manizales", "pereira": "Pereira",
    "ibague": "Ibagué", "ibagué": "Ibagué",
}


def order_city(o: dict) -> str:
    addr = o.get("shipping_address") or o.get("billing_address") or {}
    raw = (addr.get("city") or "").strip().lower()
    if not raw:
        return "(sin ciudad)"
    return CITY_NORMALIZATIONS.get(raw, raw.title())


def order_date_bog(o: dict) -> date:
    iso = o.get("created_at", "")
    if not iso:
        return date.min
    dt = datetime.fromisoformat(iso)
    return dt.astimezone(timezone(timedelta(hours=-5))).date()


def order_products(o: dict) -> list[tuple[str, int, float]]:
    out = []
    for li in o.get("line_items", []) or []:
        title = (li.get("title") or li.get("name") or "?").strip()
        qty = int(li.get("quantity", 0) or 0)
        price = float(li.get("price", 0) or 0)
        out.append((title, qty, qty * price))
    return out


def aggregate(orders: list[dict], start: date, end: date) -> dict:
    in_range = [o for o in orders if start <= order_date_bog(o) <= end]
    revenue = sum(order_revenue(o) for o in in_range)
    n = len(in_range)
    return {"orders": n, "revenue": revenue, "aov": (revenue / n) if n else 0}


def breakdown_by(orders: list[dict], key_fn) -> list[dict]:
    by: dict[str, dict] = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    for o in orders:
        k = key_fn(o)
        by[k]["orders"] += 1
        by[k]["revenue"] += order_revenue(o)
    rows = [{"key": k, **v} for k, v in by.items()]
    rows.sort(key=lambda r: -r["revenue"])
    return rows


def top_products(orders: list[dict], n: int = 10) -> list[dict]:
    agg: dict[str, dict] = defaultdict(lambda: {"qty": 0, "revenue": 0.0})
    for o in orders:
        for title, qty, total in order_products(o):
            agg[title]["qty"] += qty
            agg[title]["revenue"] += total
    rows = [{"title": t, **v} for t, v in agg.items()]
    rows.sort(key=lambda r: -r["revenue"])
    return rows[:n]


def collect():
    today = bogota_today()
    since_dt = today - timedelta(days=PULL_DAYS - 1)
    since = f"{since_dt.isoformat()}T00:00:00{TZ_OFFSET}"
    until = f"{(today + timedelta(days=1)).isoformat()}T00:00:00{TZ_OFFSET}"

    print(f"[shopify] fetching orders {since_dt} → {today} ({PULL_DAYS}d)...")
    c = ShopifyClient()
    orders = c.fetch_all(
        "orders",
        status="any",
        financial_status="paid",
        created_at_min=since,
        created_at_max=until,
    )
    print(f"[shopify] {len(orders)} orders pagados")

    # Períodos current/prev por granularidad
    p = periods_today(today)
    totals_by_period = {}
    for label, per in p.items():
        totals_by_period[label] = {
            "current": aggregate(orders, per.current_start, per.current_end),
            "prev": aggregate(orders, per.prev_start, per.prev_end),
            "granularity_label": per.granularity_label,
            "current_range": [per.current_start.isoformat(), per.current_end.isoformat()],
            "prev_range": [per.prev_start.isoformat(), per.prev_end.isoformat()],
        }

    # Time series 18d / 18w / 18m
    daily_18 = [
        {"date": s.isoformat(), **{k: v for k, v in aggregate(orders, s, e).items() if k != "aov"}}
        for s, e in last_n_days(18, today)
    ]
    weekly_18 = [
        {"week_start": label, **{k: v for k, v in aggregate(orders, s, e).items() if k != "aov"}}
        for s, e, label in last_n_weeks(18, today)
    ]
    monthly_18 = [
        {"month": label, **{k: v for k, v in aggregate(orders, s, e).items() if k != "aov"}}
        for s, e, label in last_n_months(18, today)
    ]

    # Breakdowns MTD (mes actual)
    month_start = today.replace(day=1)
    mtd_orders = [o for o in orders if order_date_bog(o) >= month_start]

    snapshot = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_bog": today.isoformat(),
        "totals_by_period": totals_by_period,
        "timeseries": {
            "daily_18": daily_18,
            "weekly_18": weekly_18,
            "monthly_18": monthly_18,
        },
        "breakdown_channel_mtd": breakdown_by(mtd_orders, classify_channel),
        "breakdown_city_mtd": breakdown_by(mtd_orders, order_city)[:15],
        "top_products_mtd": top_products(mtd_orders, n=10),
    }

    out = ROOT / "data" / "current" / "shopify.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    print(f"[shopify] → {out.relative_to(ROOT)}")

    out_hist = ROOT / "data" / "history" / f"{today.isoformat()}.json"
    out_hist.parent.mkdir(parents=True, exist_ok=True)
    out_hist.write_text(json.dumps(totals_by_period, indent=2, ensure_ascii=False))
    return snapshot


if __name__ == "__main__":
    collect()

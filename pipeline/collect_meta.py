"""Pull Meta insights con granularidad día/semana/mes para dashboard v2.

Estrategia: Meta API soporta time_increment=1 (diario) o 'monthly'. Pulleamos:
  - Diario últimos 126 días → suficiente para 18 días + 18 semanas
  - Mensual últimos 18 meses (separado, eficiente)

Output: data/current/meta.json con shape espejo a shopify.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from _periods import periods_today, last_n_days, last_n_weeks, last_n_months, bogota_today

ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
ACCOUNT = os.environ.get("META_AD_ACCOUNT_ID", "act_1628816211361333")
API_VERSION = os.environ.get("META_API_VERSION", "v21.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"

DAILY_PULL_DAYS = 126  # 18 semanas


def get_insights(since: date, until: date, level: str = "ad", time_increment=None) -> list[dict]:
    url = f"{BASE}/{ACCOUNT}/insights"
    fields = [
        "ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name",
        "spend", "impressions", "clicks", "actions", "action_values", "date_start", "date_stop",
    ]
    params = {
        "access_token": ACCESS_TOKEN,
        "level": level,
        "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
        "fields": ",".join(fields),
        "limit": 500,
    }
    if time_increment is not None:
        params["time_increment"] = time_increment
    out: list[dict] = []
    while url:
        r = requests.get(url, params=params if "?" not in url else None, timeout=60)
        if r.status_code == 429:
            time.sleep(15)
            continue
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("data", []))
        url = d.get("paging", {}).get("next")
        params = None
    return out


def parse_metrics(ins: dict) -> dict:
    """UN solo action_type ('purchase') para evitar bug de dedup."""
    spend = float(ins.get("spend", 0) or 0)
    purchases = 0
    value = 0.0
    for a in ins.get("actions", []) or []:
        if a.get("action_type") == "purchase":
            purchases = int(a.get("value", 0) or 0)
            break
    for av in ins.get("action_values", []) or []:
        if av.get("action_type") == "purchase":
            value = float(av.get("value", 0) or 0)
            break
    impr = int(ins.get("impressions") or 0)
    clk = int(ins.get("clicks") or 0)
    return {
        "spend": spend, "purchases": purchases, "purchase_value": value,
        "impressions": impr, "clicks": clk,
        "ctr": (clk / impr * 100) if impr else 0,
        "roas": (value / spend) if spend else 0,
        "cpa": (spend / purchases) if purchases else 0,
    }


def aggregate_rows(rows: list[dict]) -> dict:
    total = {"spend": 0.0, "purchases": 0, "purchase_value": 0.0, "impressions": 0, "clicks": 0}
    for ins in rows:
        m = parse_metrics(ins)
        for k in total:
            total[k] += m[k]
    total["ctr"] = (total["clicks"] / total["impressions"] * 100) if total["impressions"] else 0
    total["roas"] = (total["purchase_value"] / total["spend"]) if total["spend"] else 0
    total["cpa"] = (total["spend"] / total["purchases"]) if total["purchases"] else 0
    return total


def filter_range(rows: list[dict], start: date, end: date) -> list[dict]:
    s, e = start.isoformat(), end.isoformat()
    return [r for r in rows if s <= r.get("date_start", "") <= e]


def collect():
    today = bogota_today()
    daily_since = today - timedelta(days=DAILY_PULL_DAYS - 1)

    print(f"[meta] daily insights {daily_since} → {today} ({DAILY_PULL_DAYS}d)...")
    daily = get_insights(daily_since, today, level="ad", time_increment=1)
    print(f"[meta] {len(daily)} ad-day rows")

    # Pull mensual de 18 meses para no abusar la API con 540 días diarios
    months_since_dt = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    # Ir 17 meses atrás desde el actual
    cursor = today.replace(day=1)
    for _ in range(17):
        prev = cursor - timedelta(days=1)
        cursor = prev.replace(day=1)
    monthly_since = cursor
    print(f"[meta] monthly insights {monthly_since} → {today}...")
    monthly_rows = get_insights(monthly_since, today, level="account", time_increment="monthly")
    print(f"[meta] {len(monthly_rows)} monthly rows")

    # Períodos
    p = periods_today(today)
    totals_by_period = {}
    for label, per in p.items():
        cur = filter_range(daily, per.current_start, per.current_end)
        prv = filter_range(daily, per.prev_start, per.prev_end)
        totals_by_period[label] = {
            "current": aggregate_rows(cur),
            "prev": aggregate_rows(prv),
            "granularity_label": per.granularity_label,
            "current_range": [per.current_start.isoformat(), per.current_end.isoformat()],
            "prev_range": [per.prev_start.isoformat(), per.prev_end.isoformat()],
        }

    # Time series
    def daily_for(s: date, e: date):
        rows = filter_range(daily, s, e)
        return aggregate_rows(rows)

    daily_18 = [
        {"date": s.isoformat(), **{k: aggregate_rows(filter_range(daily, s, e))[k]
                                   for k in ["spend", "purchases", "purchase_value", "impressions", "clicks", "roas"]}}
        for s, e in last_n_days(18, today)
    ]
    weekly_18 = [
        {"week_start": label, **{k: aggregate_rows(filter_range(daily, s, e))[k]
                                  for k in ["spend", "purchases", "purchase_value", "impressions", "clicks", "roas"]}}
        for s, e, label in last_n_weeks(18, today)
    ]
    # Para mensual: mapear los monthly_rows directamente (Meta los entrega aggregados)
    by_month: dict[str, dict] = {}
    for r in monthly_rows:
        ds = r.get("date_start", "")
        if len(ds) >= 7:
            month_key = ds[:7]  # YYYY-MM
        else:
            continue
        if month_key not in by_month:
            by_month[month_key] = aggregate_rows([])
        m = parse_metrics(r)
        for k in ("spend", "purchases", "purchase_value", "impressions", "clicks"):
            by_month[month_key][k] += m[k]
    # Recalcular ratios
    for k, v in by_month.items():
        v["ctr"] = (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0
        v["roas"] = (v["purchase_value"] / v["spend"]) if v["spend"] else 0
        v["cpa"] = (v["spend"] / v["purchases"]) if v["purchases"] else 0

    monthly_18 = []
    for s, e, label in last_n_months(18, today):
        agg = by_month.get(label, aggregate_rows([]))
        monthly_18.append({
            "month": label,
            **{k: agg[k] for k in ["spend", "purchases", "purchase_value", "impressions", "clicks", "roas"]},
        })

    # MTD breakdowns: top ads + campañas
    month_start = today.replace(day=1)
    mtd_rows = filter_range(daily, month_start, today)

    by_ad: dict[str, dict] = {}
    for ins in mtd_rows:
        ad_id = ins.get("ad_id", "")
        if ad_id not in by_ad:
            by_ad[ad_id] = {
                "ad_id": ad_id, "ad_name": ins.get("ad_name", ""),
                "campaign_name": ins.get("campaign_name", ""),
                "adset_name": ins.get("adset_name", ""),
                "spend": 0.0, "purchases": 0, "purchase_value": 0.0,
                "impressions": 0, "clicks": 0,
            }
        m = parse_metrics(ins)
        for k in ("spend", "purchases", "purchase_value", "impressions", "clicks"):
            by_ad[ad_id][k] += m[k]
    for ad in by_ad.values():
        ad["ctr"] = (ad["clicks"] / ad["impressions"] * 100) if ad["impressions"] else 0
        ad["roas"] = (ad["purchase_value"] / ad["spend"]) if ad["spend"] else 0
        ad["cpa"] = (ad["spend"] / ad["purchases"]) if ad["purchases"] else 0
    top_ads = sorted(by_ad.values(), key=lambda r: -r["spend"])

    by_camp: dict[str, dict] = defaultdict(lambda: {
        "spend": 0.0, "purchases": 0, "purchase_value": 0.0,
        "impressions": 0, "clicks": 0, "ads": set()
    })
    for ins in mtd_rows:
        c = ins.get("campaign_name", "?")
        m = parse_metrics(ins)
        for k in ("spend", "purchases", "purchase_value", "impressions", "clicks"):
            by_camp[c][k] += m[k]
        by_camp[c]["ads"].add(ins.get("ad_id", ""))
    campaigns_mtd = []
    for name, v in by_camp.items():
        campaigns_mtd.append({
            "campaign": name,
            "spend": v["spend"], "purchases": v["purchases"],
            "purchase_value": v["purchase_value"],
            "impressions": v["impressions"], "clicks": v["clicks"],
            "ads_count": len(v["ads"]),
            "ctr": (v["clicks"] / v["impressions"] * 100) if v["impressions"] else 0,
            "roas": (v["purchase_value"] / v["spend"]) if v["spend"] else 0,
            "cpa": (v["spend"] / v["purchases"]) if v["purchases"] else 0,
        })
    campaigns_mtd.sort(key=lambda r: -r["spend"])

    snapshot = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_bog": today.isoformat(),
        "totals_by_period": totals_by_period,
        "timeseries": {
            "daily_18": daily_18,
            "weekly_18": weekly_18,
            "monthly_18": monthly_18,
        },
        "top_ads_mtd": top_ads,
        "campaigns_mtd": campaigns_mtd,
    }
    out = ROOT / "data" / "current" / "meta.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
    print(f"[meta] → {out.relative_to(ROOT)}")
    return snapshot


if __name__ == "__main__":
    collect()

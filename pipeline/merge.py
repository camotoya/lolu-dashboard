"""Merge shopify.json + meta.json en dashboard.json (shape v2)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DC = ROOT / "data" / "current"


def load_or_empty(name: str) -> dict:
    p = DC / name
    return json.loads(p.read_text()) if p.exists() else {}


def combo_kpis(sh_period: dict, me_period: dict) -> dict:
    sh_cur = sh_period.get("current", {"orders": 0, "revenue": 0, "aov": 0})
    sh_prv = sh_period.get("prev", {"orders": 0, "revenue": 0, "aov": 0})
    me_cur = me_period.get("current", {})
    me_prv = me_period.get("prev", {})

    def pct(c, p):
        return ((c - p) / p * 100) if p else None

    cur = {
        "orders": sh_cur.get("orders", 0),
        "revenue": sh_cur.get("revenue", 0),
        "aov": sh_cur.get("aov", 0),
        "spend_meta": me_cur.get("spend", 0),
        "meta_paid_purchases": me_cur.get("purchases", 0),
        "meta_paid_revenue": me_cur.get("purchase_value", 0),
        "roas_meta_paid": me_cur.get("roas", 0),
        "cpa_meta_paid": me_cur.get("cpa", 0),
        "ctr_meta": me_cur.get("ctr", 0),
        "roas_blended": (sh_cur.get("revenue", 0) / me_cur.get("spend", 1)) if me_cur.get("spend") else 0,
        "cpa_blended": (me_cur.get("spend", 0) / sh_cur.get("orders", 0)) if sh_cur.get("orders") else 0,
    }
    prv = {
        "orders": sh_prv.get("orders", 0),
        "revenue": sh_prv.get("revenue", 0),
        "aov": sh_prv.get("aov", 0),
        "spend_meta": me_prv.get("spend", 0),
        "meta_paid_purchases": me_prv.get("purchases", 0),
        "meta_paid_revenue": me_prv.get("purchase_value", 0),
        "roas_meta_paid": me_prv.get("roas", 0),
        "cpa_meta_paid": me_prv.get("cpa", 0),
        "ctr_meta": me_prv.get("ctr", 0),
        "roas_blended": (sh_prv.get("revenue", 0) / me_prv.get("spend", 1)) if me_prv.get("spend") else 0,
        "cpa_blended": (me_prv.get("spend", 0) / sh_prv.get("orders", 0)) if sh_prv.get("orders") else 0,
    }
    deltas = {
        "orders": pct(cur["orders"], prv["orders"]),
        "revenue": pct(cur["revenue"], prv["revenue"]),
        "aov": pct(cur["aov"], prv["aov"]),
        "spend_meta": pct(cur["spend_meta"], prv["spend_meta"]),
        "roas_blended": pct(cur["roas_blended"], prv["roas_blended"]),
        "roas_meta_paid": pct(cur["roas_meta_paid"], prv["roas_meta_paid"]),
        "cpa_meta_paid": pct(cur["cpa_meta_paid"], prv["cpa_meta_paid"]),
    }
    return {
        "current": cur, "prev": prv, "deltas": deltas,
        "granularity_label": sh_period.get("granularity_label", ""),
        "current_range": sh_period.get("current_range"),
        "prev_range": sh_period.get("prev_range"),
    }


def merge_timeseries(sh_ts: list[dict], me_ts: list[dict], key: str) -> list[dict]:
    """Une series por key (date / week_start / month). Devuelve combinado."""
    by_k = {}
    for r in sh_ts:
        k = r[key]
        by_k[k] = {key: k, "orders": r.get("orders", 0), "revenue": r.get("revenue", 0)}
    for r in me_ts:
        k = r[key]
        d = by_k.setdefault(k, {key: k, "orders": 0, "revenue": 0})
        d["spend"] = r.get("spend", 0)
        d["purchases_meta"] = r.get("purchases", 0)
        d["purchase_value_meta"] = r.get("purchase_value", 0)
        d["roas_meta_paid"] = r.get("roas", 0)
    # Calcular AOV y ROAS blended para cada punto
    for d in by_k.values():
        d["aov"] = (d["revenue"] / d["orders"]) if d.get("orders") else 0
        d["roas_blended"] = (d["revenue"] / d["spend"]) if d.get("spend") else 0
    # ordenar por la key (lex sort funciona para fechas ISO)
    return sorted(by_k.values(), key=lambda x: x[key])


def merge():
    shopify = load_or_empty("shopify.json")
    meta = load_or_empty("meta.json")

    sh_periods = shopify.get("totals_by_period", {})
    me_periods = meta.get("totals_by_period", {})

    kpis = {}
    for label in ("day", "week", "month"):
        kpis[label] = combo_kpis(sh_periods.get(label, {}), me_periods.get(label, {}))

    sh_ts = shopify.get("timeseries", {})
    me_ts = meta.get("timeseries", {})

    timeseries = {
        "daily_18": merge_timeseries(sh_ts.get("daily_18", []), me_ts.get("daily_18", []), "date"),
        "weekly_18": merge_timeseries(sh_ts.get("weekly_18", []), me_ts.get("weekly_18", []), "week_start"),
        "monthly_18": merge_timeseries(sh_ts.get("monthly_18", []), me_ts.get("monthly_18", []), "month"),
    }

    dashboard = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_bog": shopify.get("today_bog") or meta.get("today_bog"),
        "kpis": kpis,
        "timeseries": timeseries,
        "shopify": {
            "breakdown_channel_mtd": shopify.get("breakdown_channel_mtd", []),
            "breakdown_city_mtd": shopify.get("breakdown_city_mtd", []),
            "top_products_mtd": shopify.get("top_products_mtd", []),
        },
        "meta": {
            "top_ads_mtd": meta.get("top_ads_mtd", []),
            "campaigns_mtd": meta.get("campaigns_mtd", []),
        },
        "sources_status": {
            "shopify": "ok" if shopify else "missing",
            "meta": "ok" if meta else "missing",
            "ga4": "pending_setup",
            "gsc": "pending_setup",
        },
    }
    out = DC / "dashboard.json"
    out.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False))
    print(f"[merge] → {out.relative_to(ROOT)}")
    return dashboard


if __name__ == "__main__":
    merge()

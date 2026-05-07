# LOLU Dashboard

Tablero diario de métricas LOLU consolidando Shopify, Meta Ads, Google Analytics 4 y Google Search Console.

## Vista pública
https://camotoya.github.io/lolu-dashboard

(Acceso protegido con password — solicitar a Camilo)

## Cómo funciona

```
┌──────────────────────────────────────────────────┐
│ GitHub Actions (cron cada 1h)                    │
│   ├─ collect_shopify.py  → data/current/*.json   │
│   ├─ collect_meta.py                              │
│   ├─ collect_ga4.py                               │
│   ├─ collect_gsc.py                               │
│   └─ merge.py            → data/current/dashboard.json
│                          → data/history/YYYY-MM-DD.json
│                                                  │
│   git commit + push  →  GitHub Pages re-deploys │
└──────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│ docs/index.html (frontend estático)              │
│   - fetch data/current/dashboard.json            │
│   - render KPIs, charts, tables                  │
└──────────────────────────────────────────────────┘
```

## KPIs trackeados

**Top KPIs (header)**
- Revenue (hoy / sem / mes / vs mes anterior)
- Orders count + AOV
- Spend Meta + ROAS paid + ROAS blended + CPA
- Sessions GA4 + Conversion rate

**Breakdowns**
- Por canal (utm_source: meta paid, ig orgánico, direct, etc.)
- Por campaña Meta + ad
- Por ciudad (top 10)
- Top queries SEO (Google Search Console)

**Vistas**
- Hoy en vivo (datos del día actual)
- Semana en curso vs anterior
- Mes en curso vs anterior y mismo mes año pasado
- Histórico 90 días time series

## Setup local

```bash
cp .env.example .env
# pegar credenciales
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline/collect_shopify.py
python pipeline/collect_meta.py
python pipeline/merge.py
# abrir docs/index.html en el navegador
```

## Stack

- **Pipeline**: Python 3.12 + requests
- **Storage**: JSON files versionados en git
- **Frontend**: HTML + Tailwind CDN + ApexCharts (sin build)
- **Hosting**: GitHub Pages
- **Cron**: GitHub Actions

## Estado

| Fuente | Status |
|---|---|
| Shopify Admin API | ✅ |
| Meta Marketing API | ✅ |
| Google Analytics 4 | ⏳ pendiente service account |
| Google Search Console | ⏳ pendiente service account |
| Google Ads (futuro) | 📋 roadmap |

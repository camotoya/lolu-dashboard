// LOLU Dashboard v2 — frontend con granularidad día/semana/mes

const DATA_URL = '../data/current/dashboard.json';
const PASSWORD_HASH = window.LOLU_PW_HASH || '';
const ROAS_BREAKEVEN = 1.67; // margen 60% LOLU

// LOLU paleta canónica (6 colores, NO inventar más)
const LOLU = {
  hueso:     '#FAFAF7',
  tinta:     '#2A2520',
  mandarina: '#E26A3A',
  pool:      '#7DB7C4',
  terracota: '#9C4A36',
  denim:     '#3B5066',
};
// Mapeo semántico de métricas → color marca (dualidad lucha/locha)
const METRIC_COLOR = {
  revenue:        LOLU.mandarina,  // conversión cálida = Mandarina
  orders:         LOLU.terracota,  // calor secundario
  aov:            LOLU.tinta,      // ticket promedio = neutro tinta
  spend:          LOLU.denim,      // costo / ancla fría
  roas_meta_paid: LOLU.mandarina,  // ROAS paid = lo que controlamos con plata
  roas_blended:   LOLU.pool,       // ROAS total = info factual fría
};

// === Auth gate ===
async function sha256(str) {
  const buf = new TextEncoder().encode(str);
  const hash = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(hash))
    .map(b => b.toString(16).padStart(2, '0')).join('');
}
async function checkPassword() {
  const input = document.getElementById('pw-input').value;
  if (!PASSWORD_HASH) {
    sessionStorage.setItem('lolu_authed', '1');
    document.getElementById('gate').style.display = 'none';
    return;
  }
  const h = await sha256(input);
  if (h === PASSWORD_HASH) {
    sessionStorage.setItem('lolu_authed', '1');
    document.getElementById('gate').style.display = 'none';
  } else {
    document.getElementById('pw-err').style.display = 'block';
  }
}
function maybeShowGate() {
  if (!PASSWORD_HASH) return;
  if (sessionStorage.getItem('lolu_authed') === '1') return;
  document.getElementById('gate').style.display = 'flex';
}
window.checkPassword = checkPassword;

// === State ===
let DATA = null;
const _qs = new URLSearchParams(location.search);
let CURRENT_PERIOD = ['day', 'week', 'month'].includes(_qs.get('p')) ? _qs.get('p') : 'week';
let CURRENT_METRIC = 'revenue';    // revenue | orders | spend | roas_blended
let TS_CHART = null;
let CHANNEL_CHART = null;

// === Formatters ===
const fmt = {
  cop: n => n == null ? '—' : '$' + Math.round(n).toLocaleString('es-CO'),
  num: n => n == null ? '—' : Math.round(n).toLocaleString('es-CO'),
  pct: n => n == null ? '—' : n.toFixed(2) + '%',
  roas: n => n == null ? '—' : n.toFixed(2) + 'x',
  date: s => {
    if (!s) return '';
    const [y, m, d] = s.split('-');
    return `${d}/${m}`;
  },
  monthLabel: s => {
    // s = "YYYY-MM"
    const [y, m] = s.split('-');
    const names = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    return `${names[parseInt(m) - 1]} ${y.slice(2)}`;
  },
  weekLabel: s => {
    // s = lunes (YYYY-MM-DD)
    const [y, m, d] = s.split('-');
    return `${d}/${m}`;
  },
};

function deltaTag(pct, lowerIsBetter = false) {
  if (pct === null || pct === undefined) return '<span class="kpi-sub">sin comparativo</span>';
  const better = lowerIsBetter ? pct < 0 : pct >= 0;
  const cls = better ? 'delta-pos' : 'delta-neg';
  const sign = pct >= 0 ? '+' : '';
  return `<span class="${cls}">${sign}${pct.toFixed(1)}%</span> vs período anterior`;
}

// === Render KPIs ===
function renderKPIs() {
  const k = DATA.kpis[CURRENT_PERIOD];
  if (!k) return;
  const cur = k.current, prv = k.prev, d = k.deltas;

  // Revenue
  document.getElementById('kpi-revenue').textContent = fmt.cop(cur.revenue);
  document.getElementById('kpi-revenue-delta').innerHTML = deltaTag(d.revenue);
  document.getElementById('kpi-revenue-prev').textContent = `Anterior: ${fmt.cop(prv.revenue)}`;

  // Orders
  document.getElementById('kpi-orders').textContent = fmt.num(cur.orders);
  document.getElementById('kpi-orders-delta').innerHTML = deltaTag(d.orders);
  document.getElementById('kpi-orders-prev').textContent = `Anterior: ${fmt.num(prv.orders)}`;

  // AOV
  document.getElementById('kpi-aov').textContent = fmt.cop(cur.aov);
  document.getElementById('kpi-aov-delta').innerHTML = deltaTag(d.aov);
  document.getElementById('kpi-aov-prev').textContent = `Anterior: ${fmt.cop(prv.aov)}`;

  // Spend
  document.getElementById('kpi-spend').textContent = fmt.cop(cur.spend_meta);
  document.getElementById('kpi-spend-delta').innerHTML = deltaTag(d.spend_meta, true);
  document.getElementById('kpi-spend-prev').textContent = `Anterior: ${fmt.cop(prv.spend_meta)}`;

  // ROAS paid (Mandarina si está por encima de breakeven, Terracota si no)
  const roasPaid = cur.roas_meta_paid;
  const colorPaid = roasPaid >= ROAS_BREAKEVEN ? LOLU.mandarina : LOLU.terracota;
  document.getElementById('kpi-roas').innerHTML = `<span style="color: ${colorPaid}">${fmt.roas(roasPaid)}</span>`;
  document.getElementById('kpi-roas-delta').innerHTML = deltaTag(d.roas_meta_paid);
  document.getElementById('kpi-roas-prev').textContent =
    `Anterior: ${fmt.roas(prv.roas_meta_paid)} · breakeven ${ROAS_BREAKEVEN}x`;

  // ROAS blended (Pool si por encima de breakeven, Terracota si no)
  const roasBld = cur.roas_blended;
  const colorBld = roasBld >= ROAS_BREAKEVEN ? LOLU.pool : LOLU.terracota;
  document.getElementById('kpi-roas-bld').innerHTML = `<span style="color: ${colorBld}">${fmt.roas(roasBld)}</span>`;
  document.getElementById('kpi-roas-bld-delta').innerHTML = deltaTag(d.roas_blended);
  document.getElementById('kpi-roas-bld-prev').textContent =
    `Anterior: ${fmt.roas(prv.roas_blended)} · revenue total / spend Meta`;

  // Range banner
  document.getElementById('range-banner').textContent = k.granularity_label || '';
  document.getElementById('header-subtitle').textContent =
    `${rangeLabel(k.current_range)} · vs ${rangeLabel(k.prev_range)}`;
}

function rangeLabel(range) {
  if (!range) return '';
  if (range[0] === range[1]) return range[0];
  return `${range[0]} → ${range[1]}`;
}

// === Render TS chart ===
function renderTimeSeries() {
  const seriesKey = {day: 'daily_18', week: 'weekly_18', month: 'monthly_18'}[CURRENT_PERIOD];
  const xKey = {day: 'date', week: 'week_start', month: 'month'}[CURRENT_PERIOD];
  const points = DATA.timeseries[seriesKey] || [];

  const labelTitles = {
    revenue:        { name: 'Revenue',       color: METRIC_COLOR.revenue,        fmt: fmt.cop },
    orders:         { name: 'Pedidos',       color: METRIC_COLOR.orders,         fmt: fmt.num },
    aov:            { name: 'AOV',           color: METRIC_COLOR.aov,            fmt: fmt.cop },
    spend:          { name: 'Spend Meta',    color: METRIC_COLOR.spend,          fmt: fmt.cop },
    roas_meta_paid: { name: 'ROAS Meta paid',color: METRIC_COLOR.roas_meta_paid, fmt: fmt.roas },
    roas_blended:   { name: 'ROAS blended',  color: METRIC_COLOR.roas_blended,   fmt: fmt.roas },
  };
  const cfg = labelTitles[CURRENT_METRIC];

  const xFormatter = {day: fmt.date, week: fmt.weekLabel, month: fmt.monthLabel}[CURRENT_PERIOD];

  const data = points.map(p => ({
    x: xFormatter(p[xKey]),
    y: parseFloat((p[CURRENT_METRIC] || 0).toFixed(2)),
    raw: p[xKey],
  }));

  const opts = {
    chart: { type: 'bar', height: 320, toolbar: { show: false }, fontFamily: 'Inter' },
    stroke: { width: 0 },
    plotOptions: { bar: { borderRadius: 4, columnWidth: '70%' } },
    dataLabels: { enabled: false },
    series: [{ name: cfg.name, data: data }],
    colors: [cfg.color],
    xaxis: { type: 'category', labels: { rotate: -30 } },
    yaxis: { labels: { formatter: v => cfg.fmt(v) } },
    tooltip: { y: { formatter: v => cfg.fmt(v) } },
    grid: { borderColor: '#efe8df' },
  };

  if (TS_CHART) {
    TS_CHART.destroy();
  }
  TS_CHART = new ApexCharts(document.querySelector('#ts-chart'), opts);
  TS_CHART.render();

  const titleMap = {day: 'Últimos 18 días', week: 'Últimas 18 semanas', month: 'Últimos 18 meses'};
  document.getElementById('chart-title').textContent = titleMap[CURRENT_PERIOD];
}

// === Channel donut ===
function renderChannel() {
  const data = DATA.shopify.breakdown_channel_mtd || [];
  // Mapear cada canal a un color de marca según semántica lucha/locha
  const channelColor = {
    meta_paid:      LOLU.mandarina,  // paid social cálido
    ig_organic:     LOLU.pool,       // social orgánico frío
    fb_organic:     LOLU.pool,
    google_paid:    LOLU.terracota,
    google_organic: LOLU.terracota,
    direct:         LOLU.denim,      // ancla / marca tipeada
    whatsapp:       LOLU.tinta,
    email:          LOLU.tinta,
    other:          LOLU.tinta,
  };
  const colors = data.map(r => channelColor[r.key] || LOLU.tinta);
  const opts = {
    chart: { type: 'donut', height: 280, fontFamily: 'Inter' },
    series: data.map(r => r.revenue),
    labels: data.map(r => r.key),
    colors,
    legend: { position: 'bottom', fontFamily: 'Inter', labels: { colors: LOLU.tinta } },
    tooltip: { y: { formatter: v => fmt.cop(v) } },
    plotOptions: { pie: { donut: { size: '62%', labels: { show: true, total: { show: true, label: 'Revenue', formatter: () => fmt.cop(data.reduce((s, r) => s + r.revenue, 0)) } } } } },
    stroke: { width: 0 },
  };
  if (CHANNEL_CHART) CHANNEL_CHART.destroy();
  CHANNEL_CHART = new ApexCharts(document.querySelector('#channel-chart'), opts);
  CHANNEL_CHART.render();
}

function renderCities() {
  const data = DATA.shopify.breakdown_city_mtd || [];
  const max = Math.max(...data.map(r => r.revenue), 1);
  document.getElementById('city-list').innerHTML = data.length ? data.map(r => `
    <div>
      <div class="flex justify-between text-sm mb-1">
        <span>${r.key}</span>
        <span style="color: var(--lolu-tinta-soft)">${r.orders} · ${fmt.cop(r.revenue)}</span>
      </div>
      <div class="h-2 bar-track rounded">
        <div class="h-2 bar-fill-pool rounded" style="width:${(r.revenue / max * 100).toFixed(1)}%"></div>
      </div>
    </div>
  `).join('') : '<div class="text-sm" style="color: var(--lolu-tinta-mute)">Sin datos</div>';
}

function renderTopAds() {
  const data = DATA.meta.top_ads_mtd || [];
  document.getElementById('top-ads-tbody').innerHTML = data.slice(0, 10).map(a => {
    const roasClass = a.purchases === 0 ? 'badge-bad' : (a.roas >= ROAS_BREAKEVEN ? 'badge-good' : 'badge-warn');
    return `
      <tr class="table-row">
        <td class="py-2 pr-2">
          <div class="font-medium text-sm">${a.ad_name || '—'}</div>
          <div class="text-xs text-stone-500">${a.campaign_name || ''}</div>
        </td>
        <td class="text-right text-sm">${fmt.cop(a.spend)}</td>
        <td class="text-right text-sm"><span class="badge ${roasClass}">${fmt.roas(a.roas)}</span></td>
        <td class="text-right text-sm">${a.cpa ? fmt.cop(a.cpa) : '—'}</td>
      </tr>
    `;
  }).join('');
}

function renderTopProducts() {
  const data = DATA.shopify.top_products_mtd || [];
  const max = Math.max(...data.map(r => r.revenue), 1);
  document.getElementById('top-products-list').innerHTML = data.length ? data.map(r => `
    <div>
      <div class="flex justify-between text-sm mb-1">
        <span>${r.title}</span>
        <span style="color: var(--lolu-tinta-soft)">qty ${r.qty} · ${fmt.cop(r.revenue)}</span>
      </div>
      <div class="h-2 bar-track rounded">
        <div class="h-2 bar-fill-mandarina rounded" style="width:${(r.revenue / max * 100).toFixed(1)}%"></div>
      </div>
    </div>
  `).join('') : '<div class="text-sm" style="color: var(--lolu-tinta-mute)">Sin datos</div>';
}

function renderCampaigns() {
  const data = DATA.meta.campaigns_mtd || [];
  document.getElementById('camps-tbody').innerHTML = data.map(c => {
    const roasClass = c.purchases === 0 ? 'badge-bad' : (c.roas >= ROAS_BREAKEVEN ? 'badge-good' : 'badge-warn');
    return `
      <tr class="table-row">
        <td class="py-2 pr-2 text-sm">${c.campaign}</td>
        <td class="text-right text-sm">${c.ads_count}</td>
        <td class="text-right text-sm">${fmt.cop(c.spend)}</td>
        <td class="text-right text-sm">${c.purchases}</td>
        <td class="text-right text-sm"><span class="badge ${roasClass}">${fmt.roas(c.roas)}</span></td>
        <td class="text-right text-sm">${fmt.pct(c.ctr)}</td>
      </tr>
    `;
  }).join('');
}

function renderSourcesStatus() {
  const s = DATA.sources_status || {};
  const labels = { shopify: 'Shopify', meta: 'Meta Ads', ga4: 'GA4', gsc: 'Search Console' };
  const badges = {
    ok: '<span class="badge badge-good">conectado</span>',
    pending_setup: '<span class="badge badge-warn">pendiente</span>',
    missing: '<span class="badge badge-bad">falla</span>',
  };
  document.getElementById('sources-status').innerHTML =
    Object.entries(s).map(([k, v]) =>
      `<div class="flex justify-between border border-stone-200 rounded px-3 py-2"><span>${labels[k] || k}</span>${badges[v] || v}</div>`
    ).join('');
}

function renderAll() {
  renderKPIs();
  renderTimeSeries();
  renderChannel();
  renderCities();
  renderTopAds();
  renderTopProducts();
  renderCampaigns();
  renderSourcesStatus();
  document.getElementById('generated-at').textContent =
    new Date(DATA.generated_at_utc).toLocaleString('es-CO', { timeZone: 'America/Bogota' });
}

// === Event handlers ===
document.querySelectorAll('.period-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.period-btn').forEach(b => {
      b.classList.remove('tab-active');
      b.classList.add('tab-inactive');
    });
    btn.classList.remove('tab-inactive');
    btn.classList.add('tab-active');
    CURRENT_PERIOD = btn.dataset.period;
    renderKPIs();
    renderTimeSeries();
  });
});

document.querySelectorAll('.chart-metric-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.chart-metric-btn').forEach(b => {
      b.classList.remove('tab-active');
      b.classList.add('tab-inactive');
    });
    btn.classList.remove('tab-inactive');
    btn.classList.add('tab-active');
    CURRENT_METRIC = btn.dataset.metric;
    renderTimeSeries();
  });
});

function applyInitialPeriodTab() {
  document.querySelectorAll('.period-btn').forEach(b => {
    b.classList.remove('tab-active');
    b.classList.add('tab-inactive');
  });
  const active = document.querySelector(`.period-btn[data-period="${CURRENT_PERIOD}"]`);
  if (active) {
    active.classList.remove('tab-inactive');
    active.classList.add('tab-active');
  }
}

async function init() {
  applyInitialPeriodTab();
  maybeShowGate();
  if (PASSWORD_HASH && sessionStorage.getItem('lolu_authed') !== '1') return;
  try {
    const r = await fetch(DATA_URL + '?t=' + Date.now());
    if (!r.ok) throw new Error(r.statusText);
    DATA = await r.json();
    renderAll();
  } catch (e) {
    document.querySelector('main').innerHTML =
      `<div class="kpi-card text-red-600">Error cargando datos: ${e.message}</div>`;
  }
}
init();

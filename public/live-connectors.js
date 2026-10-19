/* QUANTENGINE live public-data bridge. Private keys stay server-side. */
(() => {
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: Number(n) < 1 ? 6 : 2 });
  const money = (n) => n == null || !Number.isFinite(Number(n)) ? '—' : '$' + fmt(Number(n));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let tickers = [];
  let currentProvider = 'coindcx';

  function addLiveStatus() {
    const pill = document.querySelector('.top .pill');
    if (pill) { pill.id = 'qeLiveStatus'; pill.textContent = 'CONNECTING · PUBLIC MARKET DATA'; }
    const note = document.querySelector('.side .note');
    if (note) note.innerHTML = 'LIVE PUBLIC DATA CONNECTORS<br/>CoinDCX · Binance · GDELT<br/>Private trading disabled';
    const marketDesc = document.querySelector('#page-terminal .grid2 .panel .head .desc');
    if (marketDesc) marketDesc.textContent = 'Live exchange candles · provider/timeframe dependent';
    const wl = document.querySelector('#assets')?.closest('.panel');
    if (wl) { const d = wl.querySelector('.head .desc'); if (d) d.textContent = 'Live crypto prices when the public exchange API responds'; }
    const globalBadge = document.querySelector('.global-accordion .hub-badge');
    if (globalBadge) { globalBadge.classList.remove('offline'); globalBadge.innerHTML = '<i></i>PUBLIC CRYPTO API'; }
  }

  function placeWatchlistInsideExplorer() {
    const panel = $('assets')?.closest('.panel');
    const target = $('marketClassGrid');
    const body = document.querySelector('.global-accordion .status-accordion-body');
    if (!panel || !target || !body || panel.dataset.movedInsideExplorer) return;
    panel.dataset.movedInsideExplorer = '1';
    panel.style.margin = '14px 0';
    panel.style.background = 'linear-gradient(145deg,rgba(12,29,44,.95),rgba(5,15,25,.95))';
    target.insertAdjacentElement('afterend', panel);
    const grid = document.querySelector('#page-terminal .grid2');
    if (grid) grid.style.gridTemplateColumns = '1fr';
  }

  async function api(path) {
    const r = await fetch(path, { headers: { accept: 'application/json' } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `API error ${r.status}`);
    return d;
  }

  async function loadStatus() {
    try {
      const s = await api('/api/status');
      const pill = $('qeLiveStatus');
      if (pill) pill.textContent = 'LIVE API · ' + s.status.toUpperCase();
      pill?.setAttribute('title', 'Public market data API is connected. Trading is disabled.');
    } catch {
      const pill = $('qeLiveStatus'); if (pill) pill.textContent = 'API SERVER OFFLINE';
    }
  }

  async function loadTickers() {
    const provider = $('qeExchangeProvider')?.value || currentProvider;
    currentProvider = provider;
    const box = $('assets');
    if (box) box.innerHTML = '<div class="desc" style="padding:12px 0">Loading live prices from ' + esc(provider) + '…</div>';
    try {
      const payload = await api('/api/crypto/tickers?provider=' + encodeURIComponent(provider));
      tickers = payload.data || [];
      const byWanted = ['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','TRXUSDT','AVAXUSDT','LINKUSDT','DOTUSDT','LTCUSDT'];
      const rank = new Map(byWanted.map((s,i) => [s,i]));
      tickers.sort((a,b) => (rank.get(a.symbol) ?? 999) - (rank.get(b.symbol) ?? 999));
      const real = tickers.slice(0, 120).map(a => ({ symbol:a.symbol, name:(a.name || a.symbol.replace(/USDT$/,'')) + ' · ' + a.exchange, type:'crypto', price:money(a.price), change:(a.changePct == null ? '—' : `${Number(a.changePct)>0?'+':''}${Number(a.changePct).toFixed(2)}%`), dir:Number(a.changePct)>0?'up':Number(a.changePct)<0?'red':'', rawPrice:a.price, rawChange:a.changePct, exchange:a.exchange }));
      if (Array.isArray(window.smartWatchlistAssets)) window.smartWatchlistAssets.splice(0, window.smartWatchlistAssets.length, ...real);
      else {
        // Top-level const arrays are lexical bindings; update the existing array through the filter's closure.
        try { smartWatchlistAssets.splice(0, smartWatchlistAssets.length, ...real); } catch {}
      }
      if (typeof filterAssets === 'function') filterAssets();
      const badge = document.querySelector('.global-accordion .hub-badge');
      if (badge) badge.innerHTML = '<i></i>' + esc(provider.toUpperCase()) + ' · ' + payload.count + ' MARKETS';
      const metrics = document.querySelectorAll('#page-terminal .metrics .metric');
      if (metrics[0]) { metrics[0].querySelector('.val').textContent = String(real.length); metrics[0].querySelectorAll('small')[1].textContent = 'Live crypto symbols'; }
      const scanner = metrics[3]?.querySelector('.val'); if (scanner) { scanner.textContent = 'LIVE'; scanner.classList.add('up'); }
      const scannerNote = metrics[3]?.querySelectorAll('small')[0]; if (scannerNote) scannerNote.textContent = 'Public market API';
      // Make live crypto tickers searchable inside the multi-asset explorer.
      const cryptoRows = tickers.slice(0, 150).map(a => ({ symbol:a.symbol, name:a.name || a.symbol, venue:a.exchange || provider, country:'Global / Multi-exchange', type:'crypto', price:a.price, changePct:a.changePct }));
      try {
        const existing = globalDemoAssets.filter(a => a.type !== 'crypto');
        globalDemoAssets.splice(0, globalDemoAssets.length, ...existing, ...cryptoRows);
        if (typeof searchGlobalMarkets === 'function') searchGlobalMarkets();
      } catch {}
      const now = new Date().toLocaleTimeString();
      const desc = document.querySelector('#assets')?.closest('.panel')?.querySelector('.head .desc');
      if (desc) desc.textContent = `${payload.count} markets · updated ${now} · ${provider}`;
    } catch (e) {
      if (box) box.innerHTML = '<div class="alert"><div>⚠</div><div><b>Live market data unavailable</b><p>' + esc(e.message) + '. This build does not replace missing API results with fake prices.</p></div></div>';
      const pill = $('qeLiveStatus'); if (pill) pill.textContent = 'LIVE DATA UNAVAILABLE';
    }
  }

  function getSelectedPair() {
    const v = $('marketPairFrame')?.value || 'BTCUSDT · 1m';
    const [symbol, interval] = v.split(' · ');
    const normalized = (symbol || 'BTCUSDT').replace(/[^A-Z0-9]/gi,'').toUpperCase();
    const valid = new Set(['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1D','1W','1M']);
    let tf = interval || '1m';
    if (tf === '1s') tf = '1m';
    if (tf === '1D') tf = '1d';
    if (tf === '1W') tf = '1w';
    if (!valid.has(interval)) tf = '1m';
    return { symbol: normalized || 'BTCUSDT', interval: tf };
  }

  async function loadNews() {
    const grid = $('newsGrid');
    if (!grid) return;
    try {
      const payload = await api('/api/news?q=' + encodeURIComponent('financial markets OR cryptocurrency OR central bank'));
      const articles = payload.articles || [];
      if (!articles.length) throw new Error('No articles returned by provider');
      grid.innerHTML = articles.map((a, i) => `<article class="news" data-cat="All"><div class="art">${i % 3 === 0 ? '🌐' : i % 3 === 1 ? '📊' : '🛰️'}</div><div class="newsbody"><small>${esc(a.domain || a.source || 'GDELT')} · ${esc(a.publishedAt || 'Latest')}</small><h3><a href="${esc(a.url || '#')}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none">${esc(a.title || 'Untitled news')}</a></h3><p>Live headline from public news discovery. Open the source for the full article.</p></div></article>`).join('');
      const desc = document.querySelector('#page-world .desc, #page-world .foot');
      if (desc) desc.textContent = `Live public news discovery · ${articles.length} articles · updated ${new Date().toLocaleTimeString()}`;
    } catch (e) {
      const desc = document.querySelector('#page-world .desc');
      if (desc) desc.textContent = `Live news feed unavailable: ${e.message}`;
    }
  }

  async function loadChart(symbolArg, intervalArg) {
    const selected = getSelectedPair();
    const symbol = symbolArg || selected.symbol;
    let interval = intervalArg || selected.interval;
    if (interval === '1D') interval = '1d';
    if (interval === '1W') interval = '1w';
    try {
      const payload = await api(`/api/crypto/klines?provider=binance&symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`);
      const rows = payload.data || [];
      if (rows.length < 2) throw new Error('Not enough candles returned');
      const svg = document.querySelector('#page-terminal .chart');
      if (!svg) return;
      const line = svg.querySelectorAll('path')[1];
      const area = svg.querySelectorAll('path')[0];
      if (!line || !area) return;
      const values = rows.map(x => x.close).filter(Number.isFinite);
      const min = Math.min(...values), max = Math.max(...values), range = max-min || 1;
      const pts = values.map((v,i) => [i*700/(values.length-1), 225 - ((v-min)/range)*190 - 12]);
      const d = pts.map((p,i) => `${i?'L':'M'}${p[0].toFixed(2)} ${p[1].toFixed(2)}`).join(' ');
      line.setAttribute('d', d); area.setAttribute('d', `${d} L700 250H0Z`);
      const title = document.querySelector('#page-terminal .grid2 .panel .head h2');
      if (title) title.textContent = `${symbol} · Live Market Overview`;
      const desc = document.querySelector('#page-terminal .grid2 .panel .head .desc');
      if (desc) desc.textContent = `Binance public candles · ${interval} · ${rows.length} candles · latest close ${money(values.at(-1))}`;
    } catch (e) {
      const desc = document.querySelector('#page-terminal .grid2 .panel .head .desc');
      if (desc) desc.textContent = `Live chart unavailable for ${symbol}: ${e.message}`;
    }
  }

  window.runQETopSearch = async function () {
    const input = $('qeTopSearchInput'), box = $('qeTopSearchResults');
    const q = (input?.value || '').trim(); if (!q) { input?.focus(); return; }
    box.hidden = false; box.innerHTML = '<div class="loading-search">Searching live reference source…</div>';
    try {
      const data = await api('/api/search?q=' + encodeURIComponent(q));
      const results = (data.results || []).map(x => `<article class="qe-result"><div class="qe-result-url">REFERENCE · ${esc(x.source)}</div><h3><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a></h3><p>${esc(x.snippet)}…</p><div class="qe-result-actions"><a href="${esc(x.url)}" target="_blank" rel="noopener">Read source ↗</a></div></article>`).join('');
      box.innerHTML = `<div><b style="color:#effaff">Results for “${esc(q)}”</b><p style="color:#9bb7ca;font-size:11px">${esc(data.note || '')}</p></div>${results || '<p>No reference matches found. Try a broader query.</p>'}<div class="qe-top-search-footer"><a target="_blank" rel="noopener" href="https://www.google.com/search?q=${encodeURIComponent(q)}">Google Web ↗</a><a target="_blank" rel="noopener" href="https://www.bing.com/search?q=${encodeURIComponent(q)}">Bing Web ↗</a><a target="_blank" rel="noopener" href="https://news.google.com/search?q=${encodeURIComponent(q)}">News ↗</a><a target="_blank" rel="noopener" href="https://scholar.google.com/scholar?q=${encodeURIComponent(q)}">Academic ↗</a></div>`;
    } catch (e) { box.innerHTML = `<p style="color:#ff9dad">Search unavailable: ${esc(e.message)}</p><a target="_blank" rel="noopener" href="https://www.google.com/search?q=${encodeURIComponent(q)}">Open Google Web ↗</a>`; }
  };

  function addProviderSelector() {
    const head = $('assets')?.closest('.panel')?.querySelector('.head');
    if (!head || $('qeExchangeProvider')) return;
    const select = document.createElement('select'); select.id = 'qeExchangeProvider'; select.className = 'search'; select.style.cssText = 'width:auto;max-width:130px;padding:8px';
    select.innerHTML = '<option value="coindcx">CoinDCX</option><option value="binance">Binance</option><option value="coingecko">CoinGecko</option>';
    select.title = 'Live public data source'; select.addEventListener('change', loadTickers);
    head.appendChild(select);
    const add = head.querySelector('button'); if (add) { add.textContent = '↻ Refresh'; add.onclick = loadTickers; }
  }

  // Globe can be rotated by touch/mouse drag; no external 3D library needed.
  function enableGlobeDrag() {
    const orb = document.querySelector('.orb'); if (!orb) return;
    orb.style.cursor = 'grab'; orb.style.touchAction = 'pan-y';
    let down = false, x = 0, y = 0, rx = 0, ry = 0;
    const start = e => { down = true; x = e.clientX; y = e.clientY; orb.style.cursor = 'grabbing'; orb.setPointerCapture?.(e.pointerId); };
    const move = e => { if (!down) return; ry += (e.clientX-x)*0.7; rx -= (e.clientY-y)*0.7; x=e.clientX; y=e.clientY; orb.style.animationPlayState='paused'; orb.style.transform=`rotateX(${rx}deg) rotateY(${ry}deg)`; };
    const end = () => { down=false; orb.style.cursor='grab'; };
    orb.addEventListener('pointerdown',start); orb.addEventListener('pointermove',move); orb.addEventListener('pointerup',end); orb.addEventListener('pointercancel',end);
    orb.title = 'Drag to rotate the interactive globe';
  }

  document.addEventListener('DOMContentLoaded', () => {
    addLiveStatus(); placeWatchlistInsideExplorer(); addProviderSelector(); enableGlobeDrag();
    loadStatus(); loadTickers(); loadChart(); loadNews();
    $('marketPairFrame')?.addEventListener('change', () => loadChart());
    document.querySelectorAll('#chartFrames .filter').forEach(b => b.addEventListener('click', () => setTimeout(() => loadChart(), 0)));
    // Refresh only periodically, respecting public API limits.
    setInterval(loadTickers, 30000);
  });
})();

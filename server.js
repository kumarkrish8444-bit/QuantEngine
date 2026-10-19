import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = Number(process.env.PORT || 3000);
app.disable('x-powered-by');
app.use(express.json({ limit: '100kb' }));
app.use(express.static(path.join(__dirname, 'public'), { extensions: ['html'] }));

const cache = new Map();
async function getJson(url, { ttlMs = 4000, headers = {} } = {}) {
  const key = url;
  const old = cache.get(key);
  if (old && Date.now() - old.at < ttlMs) return old.data;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(url, { headers: { 'accept': 'application/json', 'user-agent': 'QUANTENGINE/1.0 (market research dashboard)', ...headers }, signal: controller.signal });
    if (!res.ok) throw new Error(`Upstream returned ${res.status}`);
    const data = await res.json();
    cache.set(key, { at: Date.now(), data });
    return data;
  } finally { clearTimeout(timeout); }
}
function sendError(res, error, provider) {
  console.error(`[${provider}]`, error?.message || error);
  return res.status(502).json({ error: `${provider} data is temporarily unavailable`, detail: 'Try again shortly. No sample values are substituted for live API results.' });
}
const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
const safeSymbol = (s) => String(s || '').trim().toUpperCase().replace(/[^A-Z0-9_\-]/g, '').slice(0, 32);

app.get('/api/status', async (_req, res) => {
  res.json({ app: 'QUANTENGINE', status: 'online', dataMode: 'live-public-api', connectors: {
    coindcx: 'public-market-data', binance: 'public-market-data', coingecko: process.env.COINGECKO_DEMO_API_KEY ? 'configured' : 'optional-key-not-set', alphaVantage: process.env.ALPHA_VANTAGE_API_KEY ? 'configured' : 'optional-key-not-set',
    webSearch: 'Wikipedia reference search + GDELT news; not a full-web index'
  }, trading: 'disabled', serverTime: new Date().toISOString() });
});

app.get('/api/crypto/tickers', async (req, res) => {
  const provider = String(req.query.provider || 'coindcx').toLowerCase();
  try {
    if (provider === 'binance') {
      const data = await getJson('https://api.binance.com/api/v3/ticker/24hr', { ttlMs: 5000 });
      const rows = data.filter(x => /USDT$/.test(x.symbol)).map(x => ({ symbol: x.symbol, name: x.symbol.replace(/USDT$/, ''), exchange: 'Binance', price: num(x.lastPrice), changePct: num(x.priceChangePercent), high24h: num(x.highPrice), low24h: num(x.lowPrice), volume: num(x.quoteVolume), source: 'Binance public API' }));
      return res.json({ provider, updatedAt: new Date().toISOString(), count: rows.length, data: rows });
    }
    if (provider === 'coingecko') {
      if (!process.env.COINGECKO_DEMO_API_KEY) return res.status(400).json({ error: 'CoinGecko Demo API key is not configured', setup: 'Add COINGECKO_DEMO_API_KEY in the server environment. CoinDCX and Binance public endpoints do not require a key for market data.' });
      const data = await getJson('https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false', { ttlMs: 30000, headers: { 'x-cg-demo-api-key': process.env.COINGECKO_DEMO_API_KEY } });
      const rows = data.map(x => ({ symbol: `${String(x.symbol).toUpperCase()}USD`, name: x.name, exchange: 'CoinGecko aggregate', price: num(x.current_price), changePct: num(x.price_change_percentage_24h), high24h: num(x.high_24h), low24h: num(x.low_24h), volume: num(x.total_volume), source: 'CoinGecko Demo API' }));
      return res.json({ provider, updatedAt: new Date().toISOString(), count: rows.length, data: rows });
    }
    const data = await getJson('https://api.coindcx.com/exchange/ticker', { ttlMs: 4000 });
    const rows = data.filter(x => /USDT$/.test(String(x.market || ''))).map(x => ({ symbol: String(x.market), name: String(x.market).replace(/USDT$/, ''), exchange: 'CoinDCX', price: num(x.last_price), changePct: num(x.change_24_hour), high24h: num(x.high), low24h: num(x.low), volume: num(x.volume), source: 'CoinDCX public API' }));
    return res.json({ provider: 'coindcx', updatedAt: new Date().toISOString(), count: rows.length, data: rows });
  } catch (e) { return sendError(res, e, provider); }
});

app.get('/api/crypto/klines', async (req, res) => {
  const provider = String(req.query.provider || 'binance').toLowerCase();
  const symbol = safeSymbol(req.query.symbol || 'BTCUSDT');
  const intervalRaw = String(req.query.interval || '1m');
  try {
    if (provider === 'coindcx') {
      const match = symbol.match(/^([A-Z0-9]+)USDT$/);
      if (!match) return res.status(400).json({ error: 'CoinDCX candle symbol must look like BTCUSDT.' });
      const allowed = new Set(['1m', '15m', '1h', '1d']);
      const interval = allowed.has(intervalRaw) ? intervalRaw : '1m';
      const pair = `B-${match[1]}_USDT`;
      const url = `https://api.coindcx.com/market_data/candles?pair=${encodeURIComponent(pair)}&interval=${interval}&limit=250`;
      const data = await getJson(url, { ttlMs: 5000 });
      const rows = data.map(x => ({ time: num(x.time), open: num(x.open), high: num(x.high), low: num(x.low), close: num(x.close), volume: num(x.volume) })).filter(x => x.time && x.close !== null).reverse();
      return res.json({ provider, symbol, interval, updatedAt: new Date().toISOString(), data: rows });
    }
    const allowed = new Set(['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1d','1w','1M']);
    const interval = allowed.has(intervalRaw) ? intervalRaw : '1m';
    const url = `https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=250`;
    const data = await getJson(url, { ttlMs: 5000 });
    const rows = data.map(x => ({ time: num(x[0]), open: num(x[1]), high: num(x[2]), low: num(x[3]), close: num(x[4]), volume: num(x[5]) }));
    return res.json({ provider: 'binance', symbol, interval, updatedAt: new Date().toISOString(), data: rows });
  } catch (e) { return sendError(res, e, `${provider} candles`); }
});

app.get('/api/search', async (req, res) => {
  const q = String(req.query.q || '').trim().slice(0, 180);
  if (!q) return res.status(400).json({ error: 'Enter a search query.' });
  try {
    const url = `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(q)}&utf8=1&format=json&srlimit=8`;
    const data = await getJson(url, { ttlMs: 60000, headers: { 'user-agent': 'QUANTENGINE/1.0 (research tool)' } });
    const results = (data.query?.search || []).map(x => ({ title: x.title, snippet: String(x.snippet || '').replace(/<[^>]*>/g, '').replace(/&quot;/g, '"').replace(/&#039;/g, "'"), url: `https://en.wikipedia.org/wiki/${encodeURIComponent(x.title.replace(/ /g, '_'))}`, source: 'Wikipedia' }));
    res.json({ query: q, results, note: 'Reference search only; this is not a full-web search engine.' });
  } catch (e) { sendError(res, e, 'Reference search'); }
});

app.get('/api/news', async (req, res) => {
  const q = String(req.query.q || 'financial markets OR cryptocurrency OR central bank').trim().slice(0, 160);
  try {
    const url = `https://api.gdeltproject.org/api/v2/doc/doc?query=${encodeURIComponent(q)}&mode=ArtList&format=json&sort=DateDesc&maxrecords=15`;
    const data = await getJson(url, { ttlMs: 60000 });
    const articles = (data.articles || []).map(a => ({ title: a.title, url: a.url, domain: a.domain, publishedAt: a.seendate, language: a.language, source: 'GDELT' }));
    res.json({ query: q, updatedAt: new Date().toISOString(), count: articles.length, articles });
  } catch (e) { sendError(res, e, 'GDELT news'); }
});

app.get('/api/stocks/quote', async (req, res) => {
  const symbol = safeSymbol(req.query.symbol || 'IBM');
  if (!process.env.ALPHA_VANTAGE_API_KEY) return res.status(400).json({ error: 'Stock data key not configured', setup: 'Set ALPHA_VANTAGE_API_KEY on the server. Free quotas and market-data delays depend on provider terms.' });
  try {
    const url = `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${encodeURIComponent(symbol)}&apikey=${encodeURIComponent(process.env.ALPHA_VANTAGE_API_KEY)}`;
    const data = await getJson(url, { ttlMs: 60000 });
    const q = data['Global Quote'];
    if (!q || !q['05. price']) return res.status(502).json({ error: data.Note || data.Information || data['Error Message'] || 'No quote returned for this symbol.' });
    res.json({ symbol, price: num(q['05. price']), change: num(q['09. change']), changePct: String(q['10. change percent'] || '').replace('%',''), asOf: q['07. latest trading day'], source: 'Alpha Vantage' });
  } catch (e) { sendError(res, e, 'Alpha Vantage'); }
});

// Explicitly do not expose private exchange keys or order-placement routes in this starter.
app.all('/api/trade/*', (_req, res) => res.status(403).json({ error: 'Trading is disabled in this build. Public market-data integration only.' }));
app.use('/api', (_req, res) => res.status(404).json({ error: 'API route not found' }));

app.get('*', (_req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));
app.listen(PORT, () => console.log(`QUANTENGINE listening on port ${PORT}`));

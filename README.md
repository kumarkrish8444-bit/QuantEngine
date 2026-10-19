# QUANTENGINE — Real Data Starter

This package replaces the frontend-only demo with a full-stack starter that preserves the supplied QUANTENGINE dashboard design and adds server-side connectors for live public market data.

## Included real integrations

- **CoinDCX public market ticker and candles** — no private key needed for these public market-data endpoints.
- **Binance public spot ticker and candles** — no API key needed for public market-data endpoints.
- **CoinGecko Demo API** — optional key in `COINGECKO_DEMO_API_KEY`; free plan has quotas/rate limits.
- **GDELT news** — public news discovery endpoint, subject to upstream availability.
- **Wikipedia reference search** — in-app reference results; this is *not* a full-web search engine. Google/Bing/News/Scholar links open their respective sites.
- **Alpha Vantage stock quote** — optional `ALPHA_VANTAGE_API_KEY`; free quota is limited and data coverage/delay depends on provider.

The UI refreshes public crypto prices periodically and loads Binance candles for the chart. Smart Watchlist is moved inside the Global Multi-Asset Explorer container. Globe supports mouse/touch drag rotation.

## Run locally

Requires Node.js 20+.

```bash
npm install
cp .env.example .env
npm start
```

Open `http://localhost:3000`.

## Deploy on Render

Create a **Web Service** from this project/repository, set Build Command to `npm install`, Start Command to `npm start`, and add environment variables only in Render's Environment settings. Render supplies `PORT` automatically. Do not upload `.env` or secrets to GitHub.

## Important limitations

- This is the first working data-connectivity layer, not a finished institutional-grade quant platform.
- Public endpoints provide market data only. **Trading/order placement is disabled** and private exchange credentials are not collected or exposed.
- Live candles are from Binance by default; selecting CoinDCX for tickers changes the watchlist source, while the chart currently uses Binance candles. CoinDCX candle support exists in the backend route for the documented supported intervals.
- Stock/FX/indices/commodities coverage requires suitable provider APIs, keys, permissions and sometimes paid market-data licences. The UI must not imply every global asset is live merely because a category is visible.
- Strategy controls, authentication/owner permissions, alert delivery, persistent user data and isolated Python execution still need production backend work before being used for real money or sensitive data.
- API availability, CORS/network policy, quotas and terms can change. The app displays an error when a live request fails instead of substituting invented live prices.

## API routes

- `GET /api/status`
- `GET /api/crypto/tickers?provider=coindcx|binance|coingecko`
- `GET /api/crypto/klines?provider=binance|coindcx&symbol=BTCUSDT&interval=1m`
- `GET /api/search?q=quantitative%20finance`
- `GET /api/news?q=financial%20markets`
- `GET /api/stocks/quote?symbol=IBM` (requires Alpha Vantage key)

## Sources

- CoinDCX official API docs: https://docs.coindcx.com/
- Binance official Spot API docs: https://developers.binance.com/en/docs/products/spot/rest-api
- CoinGecko API pricing/docs: https://www.coingecko.com/en/api/pricing
- Alpha Vantage support/limits: https://www.alphavantage.co/support/
- GDELT API docs: https://blog.gdeltproject.org/gdelt-2-0-api-debuts/

# QuantEngine v2

## Included
- TradingView-style candlestick workspace using Lightweight Charts, with timeframe buttons from 1 minute through 1 month (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1D, 1W, 1M).
- CoinDCX public spot snapshot.
- Your 1D USDT futures opposite-break strategy (no automatic orders).
- RSI/EMA technical scanner.
- Risk/position calculator.
- 3D animated visual using Three.js plus CSS fallback.
- Admin page at `/admin`.

## Deploy to Render
1. Put `server.py`, `index.html`, `admin.html`, `requirements.txt` and `render.yaml` in the root of the GitHub repository.
2. In Render, use the repo and deploy. Build command: `pip install -r requirements.txt`; start command: `gunicorn server:app --workers 1 --threads 8 --timeout 120`.
3. In Render > Environment set:
   - `ADMIN_USERNAME` = a username you choose (default in render.yaml is `admin`)
   - `ADMIN_PASSWORD` = a strong, unique password
   - `SECRET_KEY` = long random secret (if not generated automatically)
4. Open `https://YOUR-SITE.onrender.com/admin` to manage the announcement and section visibility.

## Important limitations
- The app uses CoinDCX public API endpoints. Exchange API responses, pair formats, resolutions, rate limits and availability may change. If the exchange returns a different format, chart or strategy data may be temporarily unavailable; check Render logs.
- Strategy logic follows the provided code: it excludes the last candle as the current/incomplete candle, uses T/A/B, sets the alert level to B Low for UP or B High for DOWN, and invalidation level to A Low/A High. It scans on the server and checks prices every five minutes. No order placement is implemented.
- Candle endpoint data is not guaranteed to be real-time or available for every selected timeframe. The UI offers 1-minute through monthly intervals, but CoinDCX may not return every interval for every pair; unsupported intervals will show a chart-data-unavailable message. Confirm exchange responses and compare a few candles before relying on any signal.
- The app has no push notifications by default; browser notifications require a separate permission/foreground support and this build shows alert state in the table.
- Render's ephemeral filesystem can reset `site_settings.json` after a restart/deploy. For persistent admin settings, attach a persistent disk and set `QUANTENGINE_SETTINGS_FILE` to a path on that disk, or move settings to a database.
- External CDN libraries (Lightweight Charts, Three.js, Google Fonts) need internet access in the visitor's browser.
- This is a research/alert dashboard, not financial advice and not an execution system.

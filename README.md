# QuantEngine starter

Responsive crypto quant dashboard with a premium dark interface, animated hero, market cards, strategy equity curve, scanner table and position risk calculator.

## Run locally
1. Install Python 3.10+.
2. In this folder run: `pip install -r requirements.txt`
3. Run: `python server.py`
4. Open `http://127.0.0.1:8000`

## Important notes
- The HTML/CSS/JavaScript front end is responsive for mobile and desktop.
- The Python Flask backend requests public CoinDCX market endpoints. API availability, symbol naming, candle parameters and response fields can change; check CoinDCX's current API docs if a route returns an error.
- The market overview currently displays last-price snapshots. Percentage changes are not fabricated; daily change displays as 0 in the backend until you wire in a verified ticker/candle comparison.
- The strategy equity curve and performance metrics are clearly illustrative sample data, not actual backtest results.
- No API secrets are needed for the public endpoints used here. Never put private API keys in frontend JavaScript.
- This project does not place orders. Do not connect live order execution without extensive testing, authentication, risk limits and explicit confirmation.


### Private Admin Login
The private panel is at `/admin`. Configure `ADMIN_PASSWORD` and `SECRET_KEY` as hosting environment variables before deploying. `ADMIN_USERNAME` defaults to `krishkumar`. Never commit credentials to source control. See `README_DEPLOY.md` for details.

"""QuantEngine Flask app. Admin credentials must be set as environment variables."""
from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
import requests, time, os, json, hmac
from pathlib import Path

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("RENDER", "") == "true", MAX_CONTENT_LENGTH=32 * 1024)
BASE = "https://api.coindcx.com"
PAIRS = [("BTC", "BTCINR"), ("ETH", "ETHINR"), ("SOL", "SOLINR"), ("XRP", "XRPINR"), ("DOGE", "DOGEINR")]
DATA_FILE = Path(os.environ.get("QUANTENGINE_SETTINGS_FILE", "site_settings.json"))
DEFAULT_SETTINGS = {"announcement": "", "show_scanner": True, "show_strategy": True}


def read_settings():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_SETTINGS, **{k: data[k] for k in DEFAULT_SETTINGS if k in data}}
    except (OSError, ValueError, TypeError):
        return DEFAULT_SETTINGS.copy()


def write_settings(data):
    clean = {
        "announcement": str(data.get("announcement", ""))[:240],
        "show_scanner": bool(data.get("show_scanner", True)),
        "show_strategy": bool(data.get("show_strategy", True)),
    }
    DATA_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def admin_configured():
    return bool(os.environ.get("ADMIN_PASSWORD")) and bool(app.secret_key)


def admin_required():
    return session.get("is_admin") is True


def public_get(path, params=None):
    r = requests.get(BASE + path, params=params, timeout=12, headers={"User-Agent": "QuantEngine/1.0"})
    r.raise_for_status()
    return r.json()

@app.get("/")
def index():
    return send_from_directory(".", "index.html")

@app.get("/admin")
def admin_page():
    return send_from_directory(".", "admin.html")

@app.get("/api/public-settings")
def public_settings():
    s = read_settings()
    return jsonify({"announcement": s["announcement"], "show_scanner": s["show_scanner"], "show_strategy": s["show_strategy"]})

@app.get("/api/admin/status")
def admin_status():
    return jsonify({"configured": admin_configured(), "authenticated": admin_required()})

@app.post("/api/admin/login")
def admin_login():
    if not admin_configured():
        return jsonify({"error": "Admin login is not configured. Set ADMIN_PASSWORD and SECRET_KEY in hosting environment variables."}), 503
    data = request.get_json(silent=True) or {}
    expected_user = os.environ.get("ADMIN_USERNAME", "krishkumar")
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))
    if hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, os.environ.get("ADMIN_PASSWORD", "")):
        session.clear()
        session["is_admin"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"error": "Username or password is incorrect."}), 401

@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify({"ok": True})

@app.get("/api/admin/settings")
def admin_get_settings():
    if not admin_required(): return jsonify({"error": "Login required."}), 401
    return jsonify(read_settings())

@app.post("/api/admin/settings")
def admin_save_settings():
    if not admin_required(): return jsonify({"error": "Login required."}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify({"error": "Invalid settings."}), 400
    try:
        return jsonify({"ok": True, "settings": write_settings(data)})
    except OSError:
        return jsonify({"error": "Could not save settings on this hosting instance."}), 500

@app.get("/api/markets")
def markets():
    try:
        data = public_get("/exchange/v1/markets_details")
        by_pair = {str(x.get("pair", "")).upper(): x for x in data if isinstance(x, dict)}
        result = []
        for symbol, pair in PAIRS:
            row = by_pair.get(pair)
            if row:
                price = row.get("last_price") or row.get("last_traded_price") or row.get("price")
                try: price = float(price)
                except (TypeError, ValueError): price = 0
                result.append({"symbol": symbol, "price": price, "change": 0, "source": "COINDCX"})
        return jsonify({"markets": result, "updated_at": int(time.time()), "note": "Price snapshot; daily change requires a candle/ticker endpoint."})
    except Exception:
        return jsonify({"markets": [], "error": "CoinDCX public market endpoint unavailable"}), 502

def rsi(values, period=14):
    if len(values) < period + 1: return None
    gains, losses = [], []
    for a, b in zip(values[-period-1:-1], values[-period:]):
        d = b-a; gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains)/period, sum(losses)/period
    if al == 0: return 100.0
    return 100 - 100/(1+ag/al)

def ema(values, period):
    if len(values) < period: return None
    alpha = 2/(period+1); val = sum(values[:period])/period
    for x in values[period:]: val = alpha*x+(1-alpha)*val
    return val

@app.get("/api/scan")
def scan():
    if not read_settings()["show_scanner"]:
        return jsonify({"results": [], "note": "Scanner temporarily disabled by site administrator."})
    tf = request.args.get("timeframe", "1h")
    interval = {"1h":"1", "4h":"5", "1d":"1"}.get(tf, "1")
    results = []
    for symbol, pair in PAIRS:
        try:
            candles = public_get("/market_data/candles", {"pair": pair, "interval": interval, "limit": 100})
            if not isinstance(candles, list) or len(candles) < 25: continue
            candles = sorted(candles, key=lambda c: int(c.get("time", 0)))
            closes = [float(c.get("close")) for c in candles if c.get("close") is not None]
            if len(closes) < 25: continue
            r = rsi(closes); e20, e50 = ema(closes, 20), ema(closes, 50)
            bias = "Neutral" if e20 is None or e50 is None else ("Bullish" if e20 > e50 else "Bearish")
            signal = "Watch"
            if r is not None and bias == "Bullish" and 45 <= r <= 68: signal = "Momentum"
            elif r is not None and bias == "Bearish" and 32 <= r <= 55: signal = "Weakness"
            elif r is not None and r >= 70: signal = "Overbought"
            elif r is not None and r <= 30: signal = "Oversold"
            results.append({"symbol": symbol, "price": closes[-1], "rsi": round(r, 2) if r is not None else None, "bias": bias, "signal": signal})
        except Exception: continue
    return jsonify({"results": results, "timeframe": tf, "note": "Rule-based research scan only; verify endpoint/timeframe compatibility before relying on results."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)

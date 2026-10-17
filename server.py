import os, time, json, hmac, threading, logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, send_from_directory, session
import requests

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY") or "CHANGE-ME-SET-SECRET-KEY-IN-RENDER"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=32 * 1024,
)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("quantengine")

ACTIVE_URL = "https://api.coindcx.com/exchange/v1/derivatives/futures/data/active_instruments?margin_currency_short_name[]=USDT"
PRICE_URL = "https://public.coindcx.com/market_data/v3/current_prices/futures/rt"
CANDLE_URL = "https://public.coindcx.com/market_data/candlesticks"
SPOT_MARKETS_URL = "https://api.coindcx.com/exchange/v1/markets_details"
SETTINGS_FILE = Path(os.environ.get("QUANTENGINE_SETTINGS_FILE", "site_settings.json"))
DEFAULT_SETTINGS = {"announcement": "", "show_scanner": True, "show_strategy": True}
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "QuantEngine/2.0"})

STATE = {
    "instruments": [], "setups": {}, "prices": {}, "alerted": set(), "disabled": set(),
    "setup_day": None, "last_setup_update": None, "last_price_update": None,
    "busy": False, "last_error": None, "lock": threading.RLock()
}
PAIRS = [("BTC", "BTCINR"), ("ETH", "ETHINR"), ("SOL", "SOLINR"), ("XRP", "XRPINR"), ("DOGE", "DOGEINR")]

def safe_json_response_error(message, status=502):
    return jsonify({"error": message}), status

def read_settings():
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict): raw = {}
        return {**DEFAULT_SETTINGS, **{k: raw[k] for k in DEFAULT_SETTINGS if k in raw}}
    except (OSError, ValueError, TypeError):
        return DEFAULT_SETTINGS.copy()

def write_settings(data):
    clean = {
        "announcement": str(data.get("announcement", ""))[:240],
        "show_scanner": bool(data.get("show_scanner", True)),
        "show_strategy": bool(data.get("show_strategy", True)),
    }
    SETTINGS_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean

def get_json(url, params=None, timeout=18):
    response = HTTP.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()

def get_active_futures():
    data = get_json(ACTIVE_URL)
    if isinstance(data, dict):
        data = data.get("data", data.get("instruments", []))
    # CoinDCX currently commonly returns a list of pair identifiers.
    pairs = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, str):
            pair = item
        elif isinstance(item, dict):
            pair = item.get("pair") or item.get("symbol") or item.get("instrument")
        else:
            pair = None
        if pair and isinstance(pair, str):
            pairs.append(pair)
    return list(dict.fromkeys(pairs))

def get_current_prices():
    data = get_json(PRICE_URL)
    if isinstance(data, dict):
        return data.get("prices", data)
    return {}

def get_daily_candles(pair, resolution="1D", days=8):
    now = int(time.time())
    params = {"pair": pair, "from": now - days*86400, "to": now, "resolution": resolution, "pcode": "f"}
    try:
        data = get_json(CANDLE_URL, params=params, timeout=20)
        if isinstance(data, dict):
            candles = data.get("data", [])
        elif isinstance(data, list):
            candles = data
        else:
            return None
        if not isinstance(candles, list):
            return None
        normalized = []
        for c in candles:
            if not isinstance(c, dict): continue
            try:
                normalized.append({
                    "time": int(float(c.get("time", c.get("timestamp", 0)))),
                    "open": float(c.get("open")), "high": float(c.get("high")),
                    "low": float(c.get("low")), "close": float(c.get("close")),
                    "volume": float(c.get("volume", 0) or 0)
                })
            except (TypeError, ValueError):
                continue
        normalized.sort(key=lambda x: x["time"])
        return normalized if len(normalized) >= 4 else None
    except Exception as exc:
        log.debug("Candle fetch failed for %s: %s", pair, exc)
        return None

def get_setup(candles):
    # Match the user's supplied strategy: exclude the current/incomplete candle.
    closed = candles[:-1]
    if len(closed) < 3: return None
    T, A, B = closed[-3], closed[-2], closed[-1]
    uptrend = T["high"] < A["high"] < B["high"] and T["low"] < A["low"] < B["low"]
    downtrend = T["high"] > A["high"] > B["high"] and T["low"] > A["low"] > B["low"]
    if uptrend:
        return {"trend":"UP", "alert_level":float(B["low"]), "stop_level":float(A["low"]),
                "break_type":"B LOW BREAK", "stop_type":"A LOW BREAK", "setup_time":B["time"],
                "a_level":float(A["low"]), "b_level":float(B["low"]), "a_high":float(A["high"]), "b_high":float(B["high"])}
    if downtrend:
        return {"trend":"DOWN", "alert_level":float(B["high"]), "stop_level":float(A["high"]),
                "break_type":"B HIGH BREAK", "stop_type":"A HIGH BREAK", "setup_time":B["time"],
                "a_level":float(A["high"]), "b_level":float(B["high"]), "a_high":float(A["high"]), "b_high":float(B["high"])}
    return None

def _build_one(pair):
    candles = get_daily_candles(pair)
    return pair, get_setup(candles) if candles else None

def build_setups():
    with STATE["lock"]:
        if STATE["busy"]: return
        STATE["busy"] = True
    try:
        instruments = get_active_futures()
        if not instruments:
            raise RuntimeError("CoinDCX returned no active USDT futures instruments.")
        setups = {}
        # Parallel requests keep the scan practical while respecting a modest concurrency.
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_build_one, pair): pair for pair in instruments}
            for fut in as_completed(futures):
                try:
                    pair, setup = fut.result()
                    if setup: setups[pair] = setup
                except Exception:
                    pass
        with STATE["lock"]:
            STATE["instruments"] = instruments
            STATE["setups"] = setups
            STATE["setup_day"] = int(time.time() // 86400)
            STATE["last_setup_update"] = int(time.time())
            STATE["alerted"].clear()
            STATE["disabled"].clear()
            STATE["last_error"] = None
        log.info("Fresh daily setups: %s of %s instruments", len(setups), len(instruments))
    except Exception as exc:
        with STATE["lock"]: STATE["last_error"] = str(exc)
        log.exception("Building setups failed")
    finally:
        with STATE["lock"]: STATE["busy"] = False

def update_prices_and_alerts():
    try:
        prices = get_current_prices()
        now = int(time.time())
        events = []
        with STATE["lock"]:
            STATE["prices"] = prices
            STATE["last_price_update"] = now
            for pair, setup in STATE["setups"].items():
                item = prices.get(pair) if isinstance(prices, dict) else None
                if isinstance(item, dict):
                    raw = item.get("ls", item.get("last_price", item.get("price")))
                else:
                    raw = item
                try: price = float(raw)
                except (TypeError, ValueError): continue
                stop_level, alert_level = setup["stop_level"], setup["alert_level"]
                if setup["trend"] == "UP":
                    invalid = price < stop_level
                    triggered = price < alert_level
                    off_reason = "A LOW BROKEN"
                else:
                    invalid = price > stop_level
                    triggered = price > alert_level
                    off_reason = "A HIGH BROKEN"
                if invalid:
                    if pair not in STATE["disabled"]:
                        STATE["disabled"].add(pair)
                        events.append({"pair":pair,"type":"OFF","trend":setup["trend"],"price":price,"level":stop_level,"message":off_reason,"time":now})
                    continue
                if triggered and pair not in STATE["alerted"] and pair not in STATE["disabled"]:
                    STATE["alerted"].add(pair)
                    events.append({"pair":pair,"type":"ALERT","trend":setup["trend"],"price":price,"level":alert_level,"message":setup["break_type"],"time":now})
            STATE["last_error"] = None
        return events
    except Exception as exc:
        with STATE["lock"]: STATE["last_error"] = str(exc)
        log.warning("Price update failed: %s", exc)
        return []

def monitor_loop():
    # Background monitor refreshes prices every five minutes and rebuilds setup at next UTC day.
    while True:
        try:
            if STATE["setup_day"] is None or int(time.time()//86400) != STATE["setup_day"]:
                build_setups()
            update_prices_and_alerts()
        except Exception:
            log.exception("Monitor loop error")
        time.sleep(300)

def start_monitor():
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        thread = threading.Thread(target=monitor_loop, name="quantengine-monitor", daemon=True)
        thread.start()

@app.get("/")
def index():
    return send_from_directory(".", "index.html")

@app.get("/admin")
def admin_page():
    return send_from_directory(".", "admin.html")

@app.get("/api/health")
def health():
    return jsonify({"ok":True,"service":"QuantEngine","time":int(time.time())})

@app.get("/api/public-settings")
def public_settings():
    s = read_settings()
    return jsonify({"announcement":s["announcement"],"show_scanner":s["show_scanner"],"show_strategy":s["show_strategy"]})

@app.get("/api/markets")
def markets():
    try:
        data = get_json(SPOT_MARKETS_URL)
        by_pair = {str(x.get("pair","")).upper():x for x in data if isinstance(x,dict)} if isinstance(data,list) else {}
        result=[]
        for symbol,pair in PAIRS:
            row=by_pair.get(pair)
            if not row: continue
            try: price=float(row.get("last_price") or row.get("last_traded_price") or row.get("price"))
            except (TypeError,ValueError): price=None
            if price is not None: result.append({"symbol":symbol,"pair":pair,"price":price,"source":"CoinDCX Spot"})
        return jsonify({"markets":result,"updated_at":int(time.time()),"note":"Spot price snapshot. Daily percentage change is not shown unless verified from the source."})
    except Exception as exc:
        return safe_json_response_error("CoinDCX market data is temporarily unavailable.")

@app.get("/api/chart")
def chart_data():
    pair = request.args.get("pair","B-BTC_USDT")
    resolution = request.args.get("resolution","60")
    allowed = {"1","3","5","15","30","60","120","240","360","720","1D","1W","1M"}
    if resolution not in allowed: resolution="1"
    # CoinDCX resolution codes are passed through; supported intervals can vary by API endpoint.
    duration = {"1":2,"3":3,"5":4,"15":7,"30":10,"60":20,"120":35,"240":60,"360":90,"720":150,"1D":220,"1W":700,"1M":1500}[resolution]
    now=int(time.time())
    params={"pair":pair,"from":now-duration*86400,"to":now,"resolution":resolution,"pcode":"f"}
    try:
        data=get_json(CANDLE_URL,params=params,timeout=20)
        candles=data.get("data",[]) if isinstance(data,dict) else data if isinstance(data,list) else []
        normalized=[]
        for c in candles:
            try:
                t=int(float(c.get("time",c.get("timestamp",0))))
                # CoinDCX candle timestamps can be seconds or milliseconds.
                if t > 10_000_000_000: t//=1000
                normalized.append({"time":t,"open":float(c["open"]),"high":float(c["high"]),"low":float(c["low"]),"close":float(c["close"]),"volume":float(c.get("volume",0) or 0)})
            except (TypeError,ValueError,KeyError): pass
        normalized.sort(key=lambda x:x["time"])
        return jsonify({"pair":pair,"resolution":resolution,"candles":normalized,"updated_at":now})
    except Exception:
        return safe_json_response_error("Candlestick data unavailable for this pair/timeframe.")

@app.get("/api/strategy")
def strategy_data():
    # Make an initial setup scan on demand if the background thread hasn't completed yet.
    if STATE["setup_day"] is None and not STATE["busy"]:
        threading.Thread(target=build_setups, daemon=True).start()
    events = update_prices_and_alerts() if STATE["setups"] else []
    with STATE["lock"]:
        setups=STATE["setups"].copy()
        prices=STATE["prices"].copy()
        alerted=STATE["alerted"].copy()
        disabled=STATE["disabled"].copy()
        payload=[]
        for pair,s in setups.items():
            item=prices.get(pair,{})
            raw=item.get("ls",item.get("last_price",item.get("price"))) if isinstance(item,dict) else item
            try: price=float(raw)
            except (TypeError,ValueError): price=None
            status="OFF" if pair in disabled else "ALERT" if pair in alerted else "WAITING"
            payload.append({"pair":pair,"coin":pair.replace("B-","").replace("_USDT","").replace("USDT",""),
                **s,"price":price,"status":status})
        payload.sort(key=lambda x:(x["status"]!="ALERT",x["pair"]))
        return jsonify({"results":payload,"events":events,"active_instruments":len(STATE["instruments"]),
            "valid_setups":len(setups),"last_setup_update":STATE["last_setup_update"],
            "last_price_update":STATE["last_price_update"],"busy":STATE["busy"],"error":STATE["last_error"],
            "rules":{"up":"B LOW BREAK → ALERT; A LOW BREAK → ALERT OFF","down":"B HIGH BREAK → ALERT; A HIGH BREAK → ALERT OFF"}})

@app.get("/api/scan")
def scan():
    tf=request.args.get("timeframe","1D")
    resolution={"15m":"15","1h":"60","4h":"240","1D":"1D"}.get(tf,"1D")
    # Reuse candle endpoint and report basic RSI/EMA snapshot for popular futures.
    pairs=["B-BTC_USDT","B-ETH_USDT","B-SOL_USDT","B-XRP_USDT","B-DOGE_USDT"]
    results=[]
    for pair in pairs:
        candles=get_daily_candles(pair,resolution=resolution,days=30) if resolution=="1D" else get_intraday_candles(pair,resolution)
        if not candles or len(candles)<20: continue
        closes=[c["close"] for c in candles]
        r=calculate_rsi(closes)
        e20=calculate_ema(closes,20); e50=calculate_ema(closes,50)
        bias="Neutral" if e20 is None or e50 is None else "Bullish" if e20>e50 else "Bearish"
        signal="Watch"
        if r is not None and bias=="Bullish" and 45<=r<=68: signal="Momentum"
        elif r is not None and bias=="Bearish" and 32<=r<=55: signal="Weakness"
        elif r is not None and r>=70: signal="Overbought"
        elif r is not None and r<=30: signal="Oversold"
        results.append({"pair":pair,"symbol":pair.replace("B-","").replace("_USDT",""),"price":closes[-1],"rsi":round(r,2) if r is not None else None,"bias":bias,"signal":signal})
    return jsonify({"results":results,"timeframe":tf,"note":"Rule-based research scan; verify exchange data and account for fees/slippage."})

def get_intraday_candles(pair,resolution):
    now=int(time.time()); days={"15":7,"60":20,"240":60}.get(resolution,20)
    try:
        data=get_json(CANDLE_URL,{"pair":pair,"from":now-days*86400,"to":now,"resolution":resolution,"pcode":"f"},timeout=20)
        arr=data.get("data",[]) if isinstance(data,dict) else data if isinstance(data,list) else []
        out=[]
        for c in arr:
            try:
                t=int(float(c.get("time",c.get("timestamp",0))))
                if t>10_000_000_000:t//=1000
                out.append({"time":t,"open":float(c["open"]),"high":float(c["high"]),"low":float(c["low"]),"close":float(c["close"]),"volume":float(c.get("volume",0) or 0)})
            except (TypeError,ValueError,KeyError):pass
        return sorted(out,key=lambda x:x["time"])
    except Exception:return None

def calculate_rsi(values,period=14):
    if len(values)<period+1:return None
    gains=[];losses=[]
    for a,b in zip(values[-period-1:-1],values[-period:]):
        d=b-a;gains.append(max(d,0));losses.append(max(-d,0))
    ag=sum(gains)/period;al=sum(losses)/period
    if al==0:return 100.0
    return 100-100/(1+ag/al)

def calculate_ema(values,period):
    if len(values)<period:return None
    alpha=2/(period+1);value=sum(values[:period])/period
    for x in values[period:]:value=alpha*x+(1-alpha)*value
    return value

@app.get("/api/admin/status")
def admin_status():
    configured=bool(os.environ.get("ADMIN_PASSWORD")) and app.secret_key!="CHANGE-ME-SET-SECRET-KEY-IN-RENDER"
    return jsonify({"configured":configured,"authenticated":session.get("is_admin") is True})

@app.post("/api/admin/login")
def admin_login():
    if not os.environ.get("ADMIN_PASSWORD") or app.secret_key=="CHANGE-ME-SET-SECRET-KEY-IN-RENDER":
        return jsonify({"error":"Render Environment में ADMIN_PASSWORD और SECRET_KEY सेट करें।"}),503
    data=request.get_json(silent=True) or {}
    expected_user=os.environ.get("ADMIN_USERNAME","admin")
    if hmac.compare_digest(str(data.get("username","")),expected_user) and hmac.compare_digest(str(data.get("password","")),os.environ.get("ADMIN_PASSWORD","")):
        session.clear();session["is_admin"]=True;session.permanent=True
        return jsonify({"ok":True})
    return jsonify({"error":"Username या password गलत है।"}),401

@app.post("/api/admin/logout")
def admin_logout():
    session.clear();return jsonify({"ok":True})

@app.get("/api/admin/settings")
def admin_get_settings():
    if session.get("is_admin") is not True:return jsonify({"error":"Login required"}),401
    return jsonify(read_settings())

@app.post("/api/admin/settings")
def admin_save_settings():
    if session.get("is_admin") is not True:return jsonify({"error":"Login required"}),401
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify({"error":"Invalid settings"}),400
    try:return jsonify({"ok":True,"settings":write_settings(data)})
    except OSError:return jsonify({"error":"Settings save nahi ho payi. Render filesystem restart par reset ho sakta hai; persistent storage use karein."}),500

if __name__ == "__main__":
    start_monitor()
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","8000")),debug=False)
else:
    # Start a daemon monitor when imported by Gunicorn/Render.
    start_monitor()

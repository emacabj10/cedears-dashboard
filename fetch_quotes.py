import json, urllib.request, urllib.error, time
from datetime import datetime

# Yahoo Finance symbol mapping — ticker local → símbolo YF
YF_MAP = {
    "AMD":"AMD","AMZN":"AMZN","BABA":"BABA","BNB":"BNB-USD",
    "BRK.B":"BRK-B","BTC":"BTC-USD","DIA":"DIA","ETH":"ETH-USD",
    "GOOGL":"GOOGL","KO":"KO","MCD":"MCD","MELI":"MELI","META":"META",
    "MSFT":"MSFT","PEP":"PEP","QQQ":"QQQ",
    "SPY":"SPY","TSLA":"TSLA","V":"V","WMT":"WMT",
    "GLD":"GLD","NVDA":"NVDA","AAPL":"AAPL","NFLX":"NFLX",
    "COIN":"COIN","ARKK":"ARKK","XOM":"XOM","JPM":"JPM",
    "BAC":"BAC","UBER":"UBER","ABNB":"ABNB","SHOP":"SHOP",
}

def calc_rsi(closes, period=10):
    if len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i-1]
        g = diff if diff > 0 else 0
        l = abs(diff) if diff < 0 else 0
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_ema(closes, period=200):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return round(ema, 2)

def calc_ema_trend(closes, period=200):
    if len(closes) < period + 10:
        return "lateral"
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    emas = []
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
        emas.append(ema)
    last10 = emas[-10:]
    slope = (last10[-1] - last10[0]) / last10[0] * 100
    if slope > 1.5: return "subiendo"
    if slope < -1.5: return "bajando"
    return "lateral"

def fetch_ticker(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2y"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) < 30:
            return None
        price     = round(closes[-1], 2)
        rsi10     = calc_rsi(closes, 10)
        rsi_prev  = calc_rsi(closes[:-1], 10)
        w_closes  = [closes[i] for i in range(0, len(closes), 5)]
        rsi_w     = calc_rsi(w_closes, 10)
        ema200    = calc_ema(closes, 200)
        ema_trend = calc_ema_trend(closes, 200)
        return {
            "price": price, "rsi10": rsi10, "rsiPrev": rsi_prev,
            "rsiW": rsi_w, "ema200": ema200, "emaTrend": ema_trend
        }
    except Exception as e:
        print(f"  Error: {e}")
        return None

# ── Leer tickers desde data.json existente ───────────────────────────────────
existing_quotes = {}
try:
    with open("data.json", "r") as f:
        existing = json.load(f)
        existing_quotes = existing.get("quotes", {})
    print(f"data.json existente con {len(existing_quotes)} tickers")
except Exception:
    print("No hay data.json previo — empezando desde cero")

# Combinar: tickers del mapa base + cualquier ticker nuevo en data.json
all_tickers = dict(YF_MAP)
for ticker in existing_quotes:
    if ticker not in all_tickers:
        # Ticker nuevo agregado desde el dashboard — intentar como símbolo directo
        sym_guess = ticker.replace(".", "-")  # BRK.B → BRK-B
        all_tickers[ticker] = sym_guess
        print(f"Ticker nuevo detectado: {ticker} → {sym_guess}")

# ── Fetch de todos los tickers ───────────────────────────────────────────────
results = {}
for ticker, sym in all_tickers.items():
    print(f"Fetching {ticker} ({sym})...")
    data = fetch_ticker(sym)
    if data:
        results[ticker] = data
        print(f"  OK — precio: {data['price']}, RSI10: {data['rsi10']}, RSI sem: {data['rsiW']}")
    else:
        # Si falla, preservar datos anteriores
        if ticker in existing_quotes:
            results[ticker] = existing_quotes[ticker]
            print(f"  FAIL — usando datos anteriores")
        else:
            print(f"  FAIL — sin datos previos, omitiendo")
    time.sleep(0.5)

# ── Guardar resultado — preservar cycles y daily ─────────────────────────────
existing_cycles = {}
existing_daily = {}
try:
    with open("data.json", "r") as f:
        _prev = json.load(f)
        existing_cycles = _prev.get("cycles", {})
        existing_daily  = _prev.get("daily", {})
except Exception:
    pass

output = {
    "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "quotes":  results,
    "cycles":  existing_cycles,
    "daily":   existing_daily,
}
with open("data.json", "w") as f:
    json.dump(output, f, indent=2)

ok = sum(1 for t in all_tickers if t in results)
print(f"\nDone — {ok}/{len(all_tickers)} tickers actualizados")

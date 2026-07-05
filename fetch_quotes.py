import json, urllib.request, urllib.error, time
from datetime import datetime

# Yahoo Finance symbol mapping — ticker local → símbolo YF
YF_MAP = {
    "AMD":"AMD","AMZN":"AMZN","BABA":"BABA","BNB":"BNB-USD",
    "BRK.B":"BRK-B","BTC":"BTC-USD","DIA":"DIA","ETH":"ETH-USD",
    "GOOGL":"GOOGL","KO":"KO","MCD":"MCD","MELI":"MELI","META":"META",
    "MSFT":"MSFT","PEP":"PEP","QQQ":"QQQ",
    "SPY":"SPY","TSLA":"TSLA","V":"V","WMT":"WMT",
    "GLD":"GLD","NU":"NU","NVDA":"NVDA","AAPL":"AAPL","INTC":"INTC",
}

# Categorías fundamentales — usadas para BB ventana adaptativa
FUND = {
    "MSFT":"excelentes","GOOGL":"excelentes","AMZN":"excelentes",
    "META":"excelentes","BRK.B":"excelentes","V":"excelentes",
    "WMT":"excelentes","MELI":"excelentes","QQQ":"excelentes",
    "SPY":"excelentes","DIA":"excelentes","BTC":"excelentes",
    "ETH":"buenos","BNB":"moderados","GLD":"buenos",
    "AMD":"buenos","KO":"buenos","PEP":"buenos",
    "MCD":"buenos","BABA":"controversiales","TSLA":"controversiales",
    "NU":"excelentes","NVDA":"excelentes","AAPL":"excelentes",
    "INTC":"moderados",
}

# ── Indicadores ───────────────────────────────────────────────────────────────
def calc_rsi(closes, period=10):
    if len(closes) < period + 1: return None
    gains = losses = 0
    for i in range(1, period + 1):
        d = closes[i] - closes[i-1]
        if d > 0: gains += d
        else: losses += abs(d)
    ag, al = gains/period, losses/period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i-1]
        ag = (ag*(period-1) + (d if d>0 else 0)) / period
        al = (al*(period-1) + (abs(d) if d<0 else 0)) / period
    if al == 0: return 100.0
    return round(100 - (100/(1+ag/al)), 2)

def calc_ema(closes, period=200):
    if len(closes) < period: return None
    k = 2/(period+1)
    ema = sum(closes[:period])/period
    for c in closes[period:]: ema = c*k + ema*(1-k)
    return round(ema, 2)

def calc_ema_trend(closes, period=200):
    if len(closes) < period+20: return "lateral"
    k = 2/(period+1)
    ema = sum(closes[:period])/period
    emas = []
    for c in closes[period:]:
        ema = c*k + ema*(1-k); emas.append(ema)
    last20 = emas[-20:]
    slope = (last20[-1]-last20[0])/last20[0]*100
    return "subiendo" if slope>1.5 else ("bajando" if slope<-1.5 else "lateral")

def calc_ema_slope(closes, period=200):
    """Slope numérico de la EMA200 sobre los últimos 20 días (% de cambio).
    Positivo = EMA subiendo. Umbral > 0.8% confirma tendencia alcista sostenida."""
    if len(closes) < period + 20: return 0.0
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    emas = []
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
        emas.append(ema)
    last20 = emas[-20:]
    return round((last20[-1] - last20[0]) / last20[0] * 100, 3)

def calc_bb_lower(closes, period=20, std=2):
    if len(closes) < period: return None
    window = closes[-period:]
    mean = sum(window)/period
    variance = sum((x-mean)**2 for x in window)/period
    return round(mean - std*(variance**0.5), 2)

def calc_bb_upper(closes, period=20, std=2):
    if len(closes) < period: return None
    window = closes[-period:]
    mean = sum(window)/period
    variance = sum((x-mean)**2 for x in window)/period
    return round(mean + std*(variance**0.5), 2)

def calc_bb_width(closes, period=20, std=2):
    if len(closes) < period*2: return None
    def width(cl):
        w = cl[-period:]
        m = sum(w)/period
        s = (sum((x-m)**2 for x in w)/period)**0.5
        return (2*std*s)/m*100
    current = width(closes)
    prev    = width(closes[:-5])
    return current, prev

def calc_poc_proxy(closes):
    window = closes[-252:] if len(closes) >= 252 else closes
    return round(min(window) * 1.15, 2)

def fetch_ticker(sym, fund="buenos"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2y"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) < 210:
            return None   # mínimo 210 para EMA200 confiable
        price      = round(closes[-1], 2)
        rsi10      = calc_rsi(closes, 10)
        rsi_prev   = calc_rsi(closes[:-1], 10)
        w_closes   = [closes[i] for i in range(0, len(closes), 5)]
        rsi_w      = calc_rsi(w_closes, 10)
        ema200     = calc_ema(closes, 200)
        ema_trend  = calc_ema_trend(closes, 200)
        ema_slope  = calc_ema_slope(closes, 200)
        bb_lo      = calc_bb_lower(closes, 20, 2)
        bb_lo_prev = calc_bb_lower(closes[:-1], 20, 2)
        bb_hi      = calc_bb_upper(closes, 20, 2)
        bb_wid     = calc_bb_width(closes, 20, 2)
        poc_proxy  = calc_poc_proxy(closes)
        price_prev = closes[-2] if len(closes) >= 2 else price

        # ── Rebote Bollinger — ventana adaptativa ────────────────────────────
        # Activos "excelentes" (más volátiles): ventana 5 velas — respuesta rápida.
        # Todos los demás (buenos, moderados, controversiales): ventana 7 velas —
        # tardan más en tocar y recuperar la banda inferior.
        # price > price_prev confirma momentum alcista — filtra dead cat bounces.
        _bb_window = 5 if fund == "excelentes" else 7
        bb_recov = False
        if bb_lo is not None and price >= bb_lo and price > price_prev:
            for lookback in range(1, _bb_window + 1):
                if len(closes) > lookback:
                    past_close = closes[-(lookback + 1)]
                    past_bb_lo = calc_bb_lower(closes[:-(lookback)], 20, 2)
                    if past_bb_lo is not None and past_close < past_bb_lo:
                        bb_recov = True
                        break

        bb_below   = price < bb_lo if bb_lo else False
        bb_above   = price > bb_hi if bb_hi else False
        bb_squeeze = (bb_wid[0] < bb_wid[1] * 0.85) if bb_wid else False
        bb_near_lo = (not bb_below) and bb_lo and ((price - bb_lo) / bb_lo * 100 < 2)

        # ── Historial RSI — ultimas 15 velas ─────────────────────────────────
        rsi_history = []
        for lookback in range(15, 0, -1):
            if len(closes) > lookback:
                past_rsi = calc_rsi(closes[:-(lookback)], 10)
                if past_rsi is not None:
                    rsi_history.append(round(past_rsi, 2))

        # ── rsi_bounced_15 ────────────────────────────────────────────────────
        # RSI tocó <=30 en las últimas 15 velas Y está subiendo desde ese mínimo.
        # Evita falsos positivos cuando el RSI bajó hace muchas velas y ahora baja de nuevo.
        _rsi_min_in_window = min(rsi_history) if rsi_history else 100
        rsi_bounced_15 = (
            rsi10 is not None
            and rsi_prev is not None
            and rsi10 > 30
            and _rsi_min_in_window <= 30
            and rsi10 > rsi_prev
        )

        # ── Divergencia alcista — ventana de 15 velas ────────────────────────
        # Mínimo de precio reciente más bajo que mínimo anterior,
        # pero RSI en ese punto más alto que RSI en el mínimo anterior.
        div_bullish = False
        if rsi10 is not None and len(closes) >= 30:
            window = 15
            rec_closes = closes[-(window + 1):-1]
            ant_closes = closes[-(window * 2 + 1):-(window + 1)]
            if len(rec_closes) == window and len(ant_closes) == window:
                idx_rec = rec_closes.index(min(rec_closes))
                idx_ant = ant_closes.index(min(ant_closes))
                min_price_rec = rec_closes[idx_rec]
                min_price_ant = ant_closes[idx_ant]
                rsi_at_rec = calc_rsi(closes[:-(window + 1) + idx_rec + 1], 10)
                rsi_at_ant = calc_rsi(closes[:-(window * 2 + 1) + idx_ant + 1], 10)
                if (rsi_at_rec is not None and rsi_at_ant is not None
                        and min_price_rec < min_price_ant
                        and (min_price_ant - min_price_rec) / min_price_ant >= 0.02
                        and rsi_at_rec > rsi_at_ant):
                    div_bullish = True

        return {
            "price": price, "rsi10": rsi10, "rsi_prev": rsi_prev,
            "rsiW": rsi_w, "ema200": ema200, "emaTrend": ema_trend, "emaSlope": ema_slope,
            "bb_lo": bb_lo, "bb_hi": bb_hi, "bb_recov": bb_recov,
            "bb_below": bb_below, "bb_above": bb_above,
            "bb_squeeze": bb_squeeze, "bb_near_lo": bb_near_lo,
            "poc_proxy": poc_proxy,
            "div_bullish": div_bullish,
            "price_prev": price_prev,
            "bb_lo_prev": bb_lo_prev,
            "rsi_bounced_15": rsi_bounced_15,
            "rsiHistory": rsi_history,
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
        sym_guess = ticker.replace(".", "-")
        all_tickers[ticker] = sym_guess
        print(f"Ticker nuevo detectado: {ticker} → {sym_guess}")

# ── Fetch de todos los tickers ───────────────────────────────────────────────
results = {}
for ticker, sym in all_tickers.items():
    print(f"Fetching {ticker} ({sym})...")
    fund = FUND.get(ticker, "buenos")
    data = fetch_ticker(sym, fund)
    if data:
        results[ticker] = data
        bb_tag  = " BB↑" if data.get("bb_recov") else ""
        div_tag = " DIV✅" if data.get("div_bullish") else ""
        print(f"  OK — precio: {data['price']} · RSI10: {data['rsi10']} · RSI sem: {data['rsiW']}{bb_tag}{div_tag}")
    else:
        if ticker in existing_quotes:
            results[ticker] = existing_quotes[ticker]
            print(f"  FAIL — usando datos anteriores")
        else:
            print(f"  FAIL — sin datos previos, omitiendo")
    time.sleep(0.5)

# ── Guardar resultado — preservar cycles y daily ─────────────────────────────
existing_cycles = {}
existing_daily  = {}
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

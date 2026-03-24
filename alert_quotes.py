import json, urllib.request, urllib.error, time, os
from datetime import datetime

# ── Config desde variables de entorno (GitHub Secrets) ───────────────────────
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID= os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Fundamentals ──────────────────────────────────────────────────────────────
FUND = {
    "MSFT":"excelentes","GOOGL":"excelentes","AMZN":"excelentes",
    "META":"excelentes","BRK.B":"excelentes","V":"excelentes",
    "WMT":"excelentes","MELI":"excelentes","QQQ":"excelentes",
    "SPY":"excelentes","DIA":"excelentes","BTC":"excelentes",
    "ETH":"excelentes","BNB":"excelentes","GLD":"excelentes",
    "AMD":"buenos","KO":"buenos","PEP":"buenos",
    "MCD":"buenos","BABA":"buenos","PYPL":"buenos","TSLA":"controversiales",
}

YF_MAP = {
    "AMD":"AMD","AMZN":"AMZN","BABA":"BABA","BNB":"BNB-USD",
    "BRK.B":"BRK-B","BTC":"BTC-USD","DIA":"DIA","ETH":"ETH-USD",
    "GOOGL":"GOOGL","KO":"KO","MCD":"MCD","MELI":"MELI","META":"META",
    "MSFT":"MSFT","PEP":"PEP","PYPL":"PYPL","QQQ":"QQQ",
    "SPY":"SPY","TSLA":"TSLA","V":"V","WMT":"WMT","GLD":"GLD",
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
    if len(closes) < period+10: return "lateral"
    k = 2/(period+1)
    ema = sum(closes[:period])/period
    emas = []
    for c in closes[period:]:
        ema = c*k + ema*(1-k); emas.append(ema)
    last10 = emas[-10:]
    slope = (last10[-1]-last10[0])/last10[0]*100
    return "subiendo" if slope>1.5 else ("bajando" if slope<-1.5 else "lateral")

def calc_bb_lower(closes, period=20, std=2):
    if len(closes) < period: return None
    window = closes[-period:]
    mean = sum(window)/period
    variance = sum((x-mean)**2 for x in window)/period
    return round(mean - std*(variance**0.5), 2)

def fetch_ticker(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
    headers = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) < 30: return None
        price     = round(closes[-1], 2)
        rsi10     = calc_rsi(closes, 10)
        rsi_prev  = calc_rsi(closes[:-1], 10)
        w_closes  = [closes[i] for i in range(0, len(closes), 5)]
        rsi_w     = calc_rsi(w_closes, 10)
        ema200    = calc_ema(closes, 200)
        ema_trend = calc_ema_trend(closes, 200)
        bb_lo     = calc_bb_lower(closes, 20, 2)
        price_below_bb = price < bb_lo if bb_lo else False
        return {
            "price":price,"rsi10":rsi10,"rsi_prev":rsi_prev,
            "rsiW":rsi_w,"ema200":ema200,"emaTrend":ema_trend,
            "bb_lo":bb_lo,"price_below_bb":price_below_bb
        }
    except Exception as e:
        print(f"  Error: {e}")
        return None

# ── Scoring ───────────────────────────────────────────────────────────────────
def score_signal(ticker, q):
    fund     = FUND.get(ticker, "buenos")
    fund_ex  = fund == "excelentes"
    fund_ok  = fund in ["excelentes","buenos"]
    price    = q["price"]
    ema200   = q["ema200"] or 1
    epct     = (price - ema200) / ema200 * 100

    score = 0
    conds = []

    # C1: RSI(10) rebotó desde <30
    rsi10    = q["rsi10"] or 50
    rsi_prev = q["rsi_prev"] or 50
    if rsi10 > 30 and rsi_prev < 30:
        score += 1
        conds.append(f"✅ RSI(10) {rsi10} — rebotó desde oversold")
    elif rsi10 <= 30:
        conds.append(f"⚠️ RSI(10) {rsi10} — en oversold sin rebote aún")
    else:
        conds.append(f"➖ RSI(10) {rsi10} — fuera de zona")

    # C2: Sin divergencia (no podemos detectar automáticamente — skip)

    # C3: BB inferior
    if q["price_below_bb"]:
        conds.append(f"⚠️ Precio bajo BB inferior (${q['bb_lo']}) — sin recuperación")
    else:
        conds.append(f"➖ Precio dentro de BB")

    # C4: EMA200
    ema_trend = q["emaTrend"]
    if epct >= 0:
        score += 1
        conds.append(f"✅ {epct:+.1f}% sobre EMA200 · {ema_trend}")
    elif ema_trend == "subiendo" and epct >= -5:
        conds.append(f"⚠️ {epct:+.1f}% bajo EMA200 · subiendo (cerca)")
    elif ema_trend == "subiendo" and fund_ex and epct >= -20:
        conds.append(f"⚠️ {epct:+.1f}% bajo EMA200 · fund. excelentes compensan")
    else:
        conds.append(f"➖ {epct:+.1f}% bajo EMA200 · {ema_trend}")

    # C5: POC — no disponible automáticamente, skip

    # Setup en formación
    forming = (rsi10 > 25 and rsi10 <= 35 and rsi_prev > rsi10)

    return score, conds, forming, epct, fund

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Sin credenciales Telegram — solo imprimiendo:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"Telegram: {r.status}")
    except Exception as e:
        print(f"Telegram error: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"CEDEARS ALERTAS — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
print(f"{'='*55}\n")

signals_found   = []
forming_found   = []
all_results     = []

# Leer data.json existente para preservar datos
existing = {}
try:
    with open("data.json","r") as f:
        dj = json.load(f)
        existing = dj.get("quotes",{})
except: pass

for ticker, sym in YF_MAP.items():
    print(f"Analizando {ticker}...", end=" ", flush=True)
    q = fetch_ticker(sym)
    if not q:
        # usar datos anteriores si existen
        if ticker in existing:
            prev = existing[ticker]
            q = {
                "price": prev.get("price",0),
                "rsi10": prev.get("rsi10",50),
                "rsi_prev": prev.get("rsiPrev",50),
                "rsiW": prev.get("rsiW",50),
                "ema200": prev.get("ema200",0),
                "emaTrend": prev.get("emaTrend","lateral"),
                "bb_lo": None, "price_below_bb": False
            }
            print("usando datos anteriores")
        else:
            print("sin datos"); continue
    else:
        print(f"RSI {q['rsi10']} · precio ${q['price']}")

    score, conds, forming, epct, fund = score_signal(ticker, q)
    all_results.append((ticker, score, forming, q, conds, epct, fund))

    if score >= 3:
        signals_found.append((ticker, score, conds, q, epct, fund))
    elif forming:
        forming_found.append((ticker, q, conds, epct, fund))

    time.sleep(0.5)

# ── Armar y enviar mensajes ───────────────────────────────────────────────────
now_str = datetime.now().strftime("%d/%m %H:%M")

if not signals_found and not forming_found:
    msg = f"📊 <b>CEDEARS — {now_str}</b>\n\nSin señales activas. Mercado sin setups confirmados."
    print("\n" + msg)
    send_telegram(msg)
else:
    # Señales activas
    for ticker, score, conds, q, epct, fund in signals_found:
        size = "Posición completa 100%" if score >= 4 else "Media posición 50%"
        emoji = "🟢" if score >= 4 else "🟡"
        msg = (
            f"{emoji} <b>SEÑAL — {ticker} ({score}/5)</b>\n"
            f"📅 {now_str} · Fundamentals: {fund}\n\n"
            + "\n".join(conds) +
            f"\n\n💰 <b>Tamaño sugerido: {size}</b>\n"
            f"💵 Precio actual: ${q['price']:,}\n"
            f"📈 RSI semanal: {q['rsiW']}"
        )
        print(f"\n{'='*40}\n{msg}")
        send_telegram(msg)
        time.sleep(0.3)

    # Setups en formación
    for ticker, q, conds, epct, fund in forming_found:
        msg = (
            f"⏳ <b>SETUP EN FORMACIÓN — {ticker}</b>\n"
            f"📅 {now_str}\n\n"
            f"RSI(10) {q['rsi10']} bajando hacia 30 ↓\n"
            f"Precio: ${q['price']:,} · EMA200: {epct:+.1f}%\n\n"
            f"👀 Estar atento — puede disparar señal en próximas velas"
        )
        print(f"\n{msg}")
        send_telegram(msg)
        time.sleep(0.3)

# Resumen
total_sig = len(signals_found)
total_form = len(forming_found)
summary = (
    f"📋 <b>Resumen {now_str}</b>\n"
    f"Señales activas: {total_sig}\n"
    f"Setups en formación: {total_form}\n"
    f"Tickers analizados: {len(all_results)}"
)
print(f"\n{summary}")
if total_sig > 0 or total_form > 0:
    send_telegram(summary)

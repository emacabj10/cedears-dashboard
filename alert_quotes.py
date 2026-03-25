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
    "BRK-B":"BRK-B","BTC":"BTC-USD","DIA":"DIA","ETH":"ETH-USD",
    "GOOGL":"GOOGL","KO":"KO","MCD":"MCD","MELI":"MELI","META":"META",
    "MSFT":"MSFT","PEP":"PEP","PYPL":"PYPL","QQQ":"QQQ",
    "SPY":"SPY","TSLA":"TSLA","V":"V","WMT":"WMT","GLD":"GLD",
}

# ── Indicadores Técnicos ──────────────────────────────────────────────────────
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
        
        return {
            "price":price,"rsi10":rsi10,"rsi_prev":rsi_prev,
            "rsiW":rsi_w,"ema200":ema200,"emaTrend":ema_trend,
            "bb_lo":bb_lo
        }
    except Exception as e:
        print(f"  Error: {e}")
        return None

# ── Lógica de Scoring y Mensajería ───────────────────────────────────────────
def process_signal(ticker, q):
    fund = FUND.get(ticker, "buenos")
    price, ema200 = q["price"], q["ema200"] or 1
    epct = (price - ema200) / ema200 * 100
    rsi10, rsi_prev = q["rsi10"] or 50, q["rsi_prev"] or 50
    bb_lo = q["bb_lo"] or 0

    score = 0
    conds = []

    # 1. RSI Logic (Corregida según imágenes)
    if rsi10 > 30 and rsi_prev <= 30:
        score += 1
        rsi_msg = f"🟢 RSI(10): {rsi10} — <b>Rebotó</b> (Cruzó de <30 a >30)"
    elif rsi10 <= 30:
        rsi_msg = f"⚠️ RSI(10): {rsi10} — <b>En oversold</b> (Sin rebote confirmado)"
    elif 31 <= rsi10 <= 38 and rsi_prev > rsi10:
        rsi_msg = f"🟡 RSI(10): {rsi10} — <b>Bajando hacia 30</b> ↓"
    else:
        rsi_msg = f"➖ RSI(10): {rsi10} — Fuera de zona"
    conds.append(rsi_msg)

    # 2. EMA200 Logic
    ema_trend = q["emaTrend"]
    if epct >= 0:
        score += 1
        conds.append(f"✅ EMA200: {epct:+.1f}% — <b>Tendencia Alcista</b> ({ema_trend})")
    else:
        conds.append(f"➖ EMA200: {epct:+.1f}% — Tendencia {ema_trend}")

    # 3. Bollinger Bands Logic
    if price < bb_lo:
        conds.append(f"⚠️ BB: Precio bajo banda inferior (${bb_lo})")
    elif price >= bb_lo and rsi10 > 30 and rsi_prev <= 30:
        score += 1
        conds.append(f"✅ BB: <b>Recuperó banda inferior</b>")
    else:
        conds.append(f"➖ BB: Dentro de bandas")

    # Condición especial: "Setup en formación"
    forming = (31 <= rsi10 <= 38 and rsi_prev > rsi10)

    return score, conds, forming, epct, fund

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"--- PREVIEW TELEGRAM ---\n{message}\n-----------------------")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: pass
    except Exception as e: print(f"Telegram error: {e}")

# ── Ejecución Principal ───────────────────────────────────────────────────────
print(f"Iniciando análisis: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

signals_found = []
forming_found = []

for ticker, sym in YF_MAP.items():
    q = fetch_ticker(sym)
    if not q: continue
    
    score, conds, forming, epct, fund = process_signal(ticker, q)
    
    if score >= 3:
        signals_found.append((ticker, score, conds, q, fund))
    elif forming:
        forming_found.append((ticker, q, conds, epct))
    
    time.sleep(0.5)

# ── Envío de Mensajes ────────────────────────────────────────────────────────
now_str = datetime.now().strftime("%d/%m %H:%M")

# 1. Alertas de Señales Confirmadas
for ticker, score, conds, q, fund in signals_found:
    size = "Posición completa 100%" if score >= 4 else "Media posición 50%"
    msg = (
        f"🟢 <b>SEÑAL — {ticker} ({score}/5)</b>\n"
        f"📅 {now_str} · Fund: {fund.capitalize()}\n\n"
        + "\n".join(conds) +
        f"\n\n💰 <b>Sugerido: {size}</b>\n"
        f"💵 Precio: ${q['price']:,} · RSI Semanal: {q['rsiW']}"
    )
    send_telegram(msg)

# 2. Alertas de Watchlist (Formación)
for ticker, q, conds, epct in forming_found:
    msg = (
        f"🟡 <b>WATCHLIST — {ticker} (2/5)</b>\n"
        f"⚠️ <b>Setup en formación:</b> El RSI está bajando a zona crítica.\n\n"
        f"• Precio: ${q['price']:,}\n"
        f"• EMA200: {epct:+.1f}%\n"
        f"• Contexto: Se acerca a banda inferior de Bollinger.\n\n"
        f"🛑 <b>Acción:</b> No operar aún, esperar rebote confirmado."
    )
    send_telegram(msg)

# 3. Resumen Diario (Si no hay nada relevante)
if not signals_found and not forming_found:
    send_telegram(f"📋 <b>Resumen {now_str}</b>\nSin señales claras. Mercado en espera.")

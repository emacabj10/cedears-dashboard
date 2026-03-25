import json, urllib.request, urllib.error, time, os
from datetime import datetime

# ── Configuración (GitHub Secrets / Entorno) ─────────────────────────────────
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID= os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Diccionario de Fundamentales ──────────────────────────────────────────────
# Basado en tu preferencia de filtrar por calidad
FUND = {
    "MSFT":"excelentes", "GOOGL":"excelentes", "AMZN":"excelentes",
    "META":"excelentes", "BRK.B":"excelentes", "V":"excelentes",
    "WMT":"excelentes", "MELI":"excelentes", "QQQ":"excelentes",
    "SPY":"excelentes", "DIA":"excelentes", "BTC":"excelentes",
    "ETH":"excelentes", "BNB":"excelentes", "GLD":"excelentes",
    "AMD":"buenos", "KO":"buenos", "PEP":"buenos",
    "MCD":"buenos", "BABA":"buenos", "PYPL":"buenos", "TSLA":"controversiales",
}

YF_MAP = {
    "AMD":"AMD", "AMZN":"AMZN", "BABA":"BABA", "BNB":"BNB-USD",
    "BRK.B":"BRK-B", "BTC":"BTC-USD", "DIA":"DIA", "ETH":"ETH-USD",
    "GOOGL":"GOOGL", "KO":"KO", "MCD":"MCD", "MELI":"MELI", "META":"META",
    "MSFT":"MSFT", "PEP":"PEP", "PYPL":"PYPL", "QQQ":"QQQ",
    "SPY":"SPY", "TSLA":"TSLA", "V":"V", "WMT":"WMT", "GLD":"GLD",
}

# ── Funciones de Cálculo Técnico ──────────────────────────────────────────────
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

# ── Procesamiento de Señales ──────────────────────────────────────────────────
def process_signal(ticker, q):
    fund = FUND.get(ticker, "buenos")
    price = q["price"]
    ema200 = q["ema200"] or 1
    epct = (price - ema200) / ema200 * 100
    rsi10 = q["rsi10"] or 50
    rsi_prev = q["rsi_prev"] or 50
    bb_lo = q["bb_lo"] or 0

    score = 0
    conds = []

    # 1. Lógica RSI (Corrección del bug: Rebote vs Bajando)
    if rsi10 > 30 and rsi_prev <= 30:
        score += 1
        rsi_txt = f"✅ RSI(10): {rsi10} — <b>Rebotó</b> (Cruzó de <30 a >30)"
    elif rsi10 <= 30:
        rsi_txt = f"⚠️ RSI(10): {rsi10} — <b>En oversold</b> (Sin rebote aún)"
    elif 31 <= rsi10 <= 38 and rsi_prev > rsi10:
        rsi_txt = f"🟡 RSI(10): {rsi10} — <b>Bajando hacia 30</b> ↓"
    else:
        rsi_txt = f"➖ RSI(10): {rsi10} — Fuera de zona"
    conds.append(rsi_txt)

    # 2. Lógica EMA200
    trend = q["emaTrend"]
    if epct >= 0:
        score += 1
        conds.append(f"✅ EMA200: {epct:+.1f}% sobre la media — <b>Tendencia {trend.capitalize()}</b>")
    else:
        conds.append(f"➖ EMA200: {epct:+.1f}% bajo la media — Tendencia {trend}")

    # 3. Lógica Bollinger (Recuperación)
    if price < bb_lo:
        conds.append(f"⚠️ BB: Precio bajo banda inferior (${bb_lo:,.2f})")
    elif price >= bb_lo and rsi10 > 30 and rsi_prev <= 30:
        score += 1
        conds.append(f"✅ BB: <b>Recuperó banda inferior</b>")
    else:
        conds.append(f"➖ BB: Dentro de bandas")

    # Determinar si es un Setup en Formación (Watchlist)
    is_forming = (31 <= rsi10 <= 38 and rsi_prev > rsi10)

    return score, conds, is_forming, epct, fund

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"\n[PREVIEW TELEGRAM]\n{message}\n")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: pass
    except Exception as e: print(f"Error Telegram: {e}")

# ── Lógica Principal (Main) ───────────────────────────────────────────────────
# (Omitida la parte de fetch_ticker por brevedad, se mantiene igual a tu original)

# ... (Dentro del bucle de tickers) ...
score, conds, forming, epct, fund = process_signal(ticker, q)
now_str = datetime.now().strftime("%d/%m %H:%M")

if score >= 3:
    # Formato SEÑAL (Score >= 3/5)
    size = "Posición completa 100%" if score >= 4 else "Media posición 50%"
    msg = (
        f"🟢 <b>SEÑAL — {ticker} ({score}/5)</b>\n"
        f"📅 {now_str} · Fundamentals: {fund.capitalize()}\n\n"
        + "\n".join(conds) +
        f"\n\n💰 <b>Tamaño sugerido: {size}</b>\n"
        f"💵 Precio actual: ${q['price']:,}\n"
        f"📈 RSI semanal: {q['rsiW']}"
    )
    send_telegram(msg)

elif forming:
    # Formato WATCHLIST (RSI bajando hacia 30)
    msg = (
        f"🟡 <b>WATCHLIST — {ticker} (2/5)</b>\n"
        f"⚠️ <b>Setup en formación:</b> El RSI está bajando hacia 30.\n\n"
        f"💵 Precio actual: ${q['price']:,}\n"
        f"📉 Contexto: Se acerca a banda inferior de Bollinger.\n"
        f"📈 EMA200: {epct:+.1f}%\n\n"
        f"🛑 <b>Acción:</b> No operar aún, esperar rebote confirmado en RSI."
    )
    send_telegram(msg)

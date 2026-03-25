import json, urllib.request, urllib.error, time, os
from datetime import datetime

# ── Configuración (GitHub Secrets) ───────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID= os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Diccionario de Fundamentales ──────────────────────────────────────────────
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
    "BRK-B":"BRK-B", "BTC":"BTC-USD", "DIA":"DIA", "ETH":"ETH-USD",
    "GOOGL":"GOOGL", "KO":"KO", "MCD":"MCD", "MELI":"MELI", "META":"META",
    "MSFT":"MSFT", "PEP":"PEP", "PYPL":"PYPL", "QQQ":"QQQ",
    "SPY":"SPY", "TSLA":"TSLA", "V":"V", "WMT":"WMT", "GLD":"GLD",
}

# ── Funciones Técnicas ────────────────────────────────────────────────────────
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
    headers = {"User-Agent":"Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        res = data["chart"]["result"][0]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) < 30: return None
        
        # Datos para RSI Semanal
        w_closes = [closes[i] for i in range(0, len(closes), 5)]
        
        return {
            "price": round(closes[-1], 2),
            "rsi10": calc_rsi(closes, 10),
            "rsi_prev": calc_rsi(closes[:-1], 10),
            "rsiW": calc_rsi(w_closes, 10),
            "ema200": calc_ema(closes, 200),
            "emaTrend": calc_ema_trend(closes, 200),
            "bb_lo": calc_bb_lower(closes, 20, 2)
        }
    except: return None

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: pass
    except Exception as e: print(f"Error Telegram: {e}")

# ── Ejecución Principal ───────────────────────────────────────────────────────
print(f"Iniciando: {datetime.now().strftime('%d/%m %H:%M')}")

for ticker, sym in YF_MAP.items():
    q = fetch_ticker(sym)
    if not q: continue
    
    # Lógica de scoring interna para evitar NameError
    fund = FUND.get(ticker, "buenos")
    price, ema200, bb_lo = q["price"], q["ema200"] or 1, q["bb_lo"] or 0
    epct = (price - ema200) / ema200 * 100
    rsi10, rsi_prev = q["rsi10"] or 50, q["rsi_prev"] or 50
    trend = q["emaTrend"]
    
    score = 0
    conds = []

    # 1. RSI (Corrección del bug)
    if rsi10 > 30 and rsi_prev <= 30:
        score += 1
        conds.append(f"✅ RSI(10): {rsi10} — <b>Rebotó</b> (Salió de <30)")
    elif rsi10 <= 30:
        conds.append(f"⚠️ RSI(10): {rsi10} — <b>En oversold</b> (Bajo 30)")
    elif 31 <= rsi10 <= 38 and rsi_prev > rsi10:
        conds.append(f"🟡 RSI(10): {rsi10} — <b>Bajando hacia 30</b> ↓")
    else:
        conds.append(f"➖ RSI(10): {rsi10} — Neutral")

    # 2. EMA200
    if epct >= 0:
        score += 1
        conds.append(f"✅ EMA200: {epct:+.1f}% sobre la media — <b>Tendencia {trend}</b>")
    else:
        conds.append(f"➖ EMA200: {epct:+.1f}% bajo la media — Tendencia {trend}")

    # 3. Bollinger
    if price < bb_lo:
        conds.append(f"⚠️ BB: Precio bajo banda inferior (${bb_lo:,.2f})")
    elif price >= bb_lo and rsi10 > 30 and rsi_prev <= 30:
        score += 1
        conds.append(f"✅ BB: <b>Recuperó banda inferior</b>")
    else:
        conds.append(f"➖ BB: Dentro de bandas")

    # Envío de alertas
    now_str = datetime.now().strftime("%d/%m %H:%M")
    
    if score >= 3:
        size = "Posición completa 100%" if score >= 4 else "Media posición 50%"
        msg = (
            f"🟢 <b>SEÑAL — {ticker} ({score}/5)</b>\n"
            f"📅 {now_str} · Fund: {fund.capitalize()}\n\n"
            + "\n".join(conds) +
            f"\n\n💰 <b>Sugerido: {size}</b>\n"
            f"💵 Precio: ${price:,} · RSI Semanal: {q['rsiW']}"
        )
        send_telegram(msg)
    
    elif (31 <= rsi10 <= 38 and rsi_prev > rsi10):
        msg = (
            f"🟡 <b>WATCHLIST — {ticker} (2/5)</b>\n"
            f"⚠️ <b>Setup en formación:</b> RSI bajando a zona crítica.\n\n"
            f"• Precio: ${price:,}\n"
            f"• EMA200: {epct:+.1f}%\n"
            f"• Contexto: Cerca de banda inferior de BB.\n\n"
            f"🛑 <b>Acción:</b> No operar aún, esperar rebote."
        )
        send_telegram(msg)
    
    time

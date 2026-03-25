import json, urllib.request, urllib.error, time, os, random
from datetime import datetime

# ── 1. CONFIGURACIÓN ──────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

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

BOT_NOTES = [
    "Día de paciencia, los setups maduran lento.",
    "El mercado da revancha, el capital no.",
    "Operá lo que ves, no lo que crees."
]

# ── 2. FUNCIONES TÉCNICAS ─────────────────────────────────────────────────────
def fetch_ticker(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
    headers = {"User-Agent":"Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())["chart"]["result"][0]
        c = [x for x in data["indicators"]["quote"][0]["close"] if x is not None]
        
        def get_rsi(prices):
            if len(prices) < 11: return 50
            g, l = 0, 0
            for i in range(1, 11):
                d = prices[i] - prices[i-1]
                if d > 0: g += d
                else: l += abs(d)
            return round(100 - (100/(1+(g/10)/(l/10))), 2) if l != 0 else 100

        ema200 = sum(c[-200:])/200 if len(c)>=200 else c[-1]
        avg20 = sum(c[-20:])/20
        std20 = (sum((x-avg20)**2 for x in c[-20:])/20)**0.5
        return {
            "price": c[-1], "rsi10": get_rsi(c), "rsi_prev": get_rsi(c[:-1]),
            "ema200": ema200, "bb_lo": avg20 - 2*std20,
            "poc_proxy": max(set(c[-50:]), key=c[-50:].count)
        }
    except: return None

def score_signal(ticker, q):
    score = 0
    # RSI Rebote (1 pto)
    if q["rsi10"] > 30 and q["rsi_prev"] <= 30: score += 1
    # EMA200 Alcista (1 pto)
    epct = ((q["price"] - q["ema200"])/q["ema200"]*100)
    if epct > 0: score += 1
    # POC Distancia (Fuerte +2, Moderada +1)
    ppct = ((q["price"] - q["poc_proxy"])/q["poc_proxy"]*100)
    if ppct <= -15: score += 2  # FUERTE: Más de -15%
    elif -15 < ppct <= -5: score += 1 # MODERADA: -5% a -15%
    # Fundamentales (1 pto)
    if FUND.get(ticker) == "excelentes": score += 1
    return score, epct, ppct

def get_labels(q, epct, ppct):
    if q["rsi10"] > 30 and q["rsi_prev"] <= 30: r_txt = f"{q['rsi10']} — Rebote confirmado."
    elif q["rsi10"] <= 30: r_txt = f"{q['rsi10']} — En sobreventa (Sin fuerza)."
    else: r_txt = f"{q['rsi10']} — Neutral."
    
    e_txt = f"{epct:+.1f}% — {'Sobre' if epct > 0 else 'Bajo'} la tendencia de largo plazo."
    p_txt = f"${q['poc_proxy']:,} — Distancia: {ppct:+.1f}%."
    b_txt = "Presionando banda inferior." if q["price"] <= q["bb_lo"] else "Rango normal."
    return r_txt, e_txt, p_txt, b_txt

def send_telegram(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try: urllib.request.urlopen(req)
    except: pass

# ── 3. EJECUCIÓN Y CLASIFICACIÓN ──────────────────────────────────────────────
h = datetime.now().hour
if h < 13: header = "☀️ <b>APERTURA - 11:00 AM</b>"
elif h < 16: header = "📊 <b>MEDIA RUEDA - 02:00 PM</b>"
else: header = "🔔 <b>CIERRE DE MERCADO - 05:00 PM</b>"

signals, watchlist, radar, all_rsi = [], [], [], []

for ticker, sym in YF_MAP.items():
    q = fetch_ticker(sym)
    if not q: continue
    score, epct, ppct = score_signal(ticker, q)
    all_rsi.append(q["rsi10"])
    
    # ── JERARQUÍA DE SCORE ──
    if score >= 3:
        signals.append((ticker, score, q, epct, ppct))
    elif score == 2:
        watchlist.append((ticker, score, q, epct, ppct))
    else:
        # Score 0 o 1 se guarda para el reporte si el RSI es bajo
        if q["rsi10"] <= 42:
            radar.append((ticker, score, q))
    time.sleep(0.5)

# ── 4. ENVÍO DE ALERTAS ───────────────────────────────────────────────────────
send_telegram(f"{header}\nIniciando escaneo técnico...")

# 🟢 SEÑAL INDIVIDUAL (Score 3 o más)
for t, s, q, e, p in signals:
    r_l, e_l, p_l, b_l = get_labels(q, e, p)
    msg = (f"🟢 <b>{t} — {s}/5</b>\n"
           f"📉 RSI: {r_l}\n📈 EMA200: {e_l}\n📊 POC: {p_l}\n🎢 BB: {b_l}\n"
           f"💡 <b>Sugerencia:</b> {'Posición completa 100%' if s>=4 else 'Media posición 50%'}")
    send_telegram(msg)

# 🟡 WATCHLIST INDIVIDUAL (Score 2)
for t, s, q, e, p in watchlist:
    r_l, e_l, p_l, b_l = get_labels(q, e, p)
    msg = (f"🟡 <b>WATCHLIST — {t} (2/5)</b>\n⚠️ Estado: Setup en formación.\n\n"
           f"📉 RSI(10): {r_l}\n📈 EMA200: {e_l}\n📊 POC: {p_l}\n🎢 BB: {b_l}\n"
           f"🛑 <b>Acción sugerida:</b> NO OPERAR. Esperar confirmación.")
    send_telegram(msg)

# 📋 REPORTE RADAR (Score 0 o 1)
avg_rsi = round(sum(all_rsi)/len(all_rsi), 1) if all_rsi else 50
radar_txt = "\n".join([f"• {t}: RSI {q['rsi10']} (Score {s}/5)" for t, s, q in radar[:6]])
msg_final = (f"📋 <b>Reporte Final — {header}</b>\n\n"
             f"<b>Radar de Seguimiento (Score 0-1):

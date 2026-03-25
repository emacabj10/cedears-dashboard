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

BOT_NOTES = ["Paciencia, los setups maduran.", "Operá lo que ves.", "Capital > Ego."]

# ── 2. FUNCIONES TÉCNICAS ─────────────────────────────────────────────────────
def fetch_ticker(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
    headers = {"User-Agent":"Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            # Validación de seguridad para el error 'chart'
            if "chart" not in resp or resp["chart"]["result"] is None:
                return None
            data = resp["chart"]["result"][0]
        
        c = [x for x in data["indicators"]["quote"][0]["close"] if x is not None]
        if len(c) < 21: return None
        
        def get_rsi(prices):
            p = prices[-11:]
            g, l = 0, 0
            for i in range(1, len(p)):
                d = p[i] - p[i-1]
                if d > 0: g += d
                else: l += abs(d)
            return round(100 - (100/(1+(g/10)/(l/10))), 2) if l != 0 else 100

        ema200 = sum(c[-200:])/200 if len(c)>=200 else c[-1]
        avg20 = sum(c[-20:])/20
        std20 = (sum((x-avg20)**2 for x in c[-20:])/20)**0.5
        avg20_prev = sum(c[-21:-1])/20
        std20_prev = (sum((x-avg20_prev)**2 for x in c[-21:-1])/20)**0.5

        return {
            "price": c[-1], "price_prev": c[-2],
            "rsi10": get_rsi(c), "rsi_prev": get_rsi(c[:-1]),
            "ema200": ema200, 
            "bb_lo": avg20 - 2*std20, "bb_lo_prev": avg20_prev - 2*std20_prev,
            "poc_proxy": max(set(c[-50:]), key=c[-50:].count)
        }
    except Exception:
        return None

def score_signal(ticker, q):
    score, tags = 0, []
    # RSI Rebote / Divergencia
    if q["rsi10"] > 30 and q["rsi_prev"] <= 30:
        score += 1
        tags.append("Rebote RSI")
    elif q["price"] < q["price_prev"] and q["rsi10"] > q["rsi_prev"]:
        score += 1
        tags.append("Divergencia")
    # EMA200
    epct = ((q["price"] - q["ema200"])/q["ema200"]*100)
    if epct > 0: 
        score += 1
        tags.append("EMA200")
    # POC
    ppct = ((q["price"] - q["poc_proxy"])/q["poc_proxy"]*100)
    if ppct <= -15: 
        score += 2
        tags.append("POC Fuerte")
    elif -15 < ppct <= -5: 
        score += 1
        tags.append("POC Mod")
    # Rebote BB
    if q["price_prev"] <= q["bb_lo_prev"] and q["price"] > q["bb_lo"]:
        score += 1
        tags.append("Rebote BB")
    # Fundamentales
    if FUND.get(ticker) == "excelentes": score += 1
        
    return score, epct, ppct, tags

def send_telegram(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req) as f: pass
    except: pass

# ── 3. EJECUCIÓN ──────────────────────────────────────────────────────────────
h = datetime.now().hour
header = "☀️ 11:00 AM" if h < 13 else "📊 02:00 PM" if h < 16 else "🔔 05:00 PM"

signals, watchlist, radar, all_rsi = [], [], [], []

for ticker, sym in YF_MAP.items():
    q = fetch_ticker(sym)
    if not q: continue
    s, e, p, t = score_signal(ticker, q)
    all_rsi.append(q["rsi10"])
    
    if s >= 3: signals.append((ticker, s, q, e, p, t))
    elif s == 2: watchlist.append((ticker, s, q, e, p, t))
    elif q["rsi10"] <= 42: radar.append((ticker, s, q))
    time.sleep(0.7) # Más delay para evitar bloqueos

# ── 4. ENVÍO ──────────────────────────────────────────────────────────────────
send_telegram(f"<b>REPORTANDO: {header}</b>")

for t, s, q, e, p, tags in signals:
    send_telegram(f"🟢 <b>{t} — {s}/5</b>\nTags: {', '.join(tags)}\nDist. POC: {p:+.1f}%")

for t, s, q, e, p, tags in watchlist:
    send_telegram(f"🟡 <b>WATCHLIST: {t} (Score 2)</b>\nSetup: {', '.join(tags)}\nPOC: {p:+.1f}%")

avg_rsi = round(sum(all_rsi)/len(all_rsi), 1) if all_rsi else 50
radar_txt = "\n".join([f"• {t}: RSI {q['rsi10']} (S:{s}/5)" for t, s, q in radar[:6]])
send_telegram(f"📋 <b>RESUMEN RADAR</b>\n{radar_txt}\n\n🌡️ RSI Prom: {avg_rsi}")

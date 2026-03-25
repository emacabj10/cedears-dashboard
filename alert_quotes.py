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
    "No fuerces trades, dejá que el precio venga a vos.",
    "El mercado da revancha, el capital no.",
    "Operá lo que ves, no lo que crees."
]

# ── 2. FUNCIONES TÉCNICAS ─────────────────────────────────────────────────────
def calc_rsi(closes, period=10):
    if len(closes) < period + 1: return 50
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
    return round(100 - (100/(1+ag/al)), 2) if al != 0 else 100

def fetch_ticker(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
    headers = {"User-Agent":"Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())["chart"]["result"][0]
        c = [x for x in data["indicators"]["quote"][0]["close"] if x is not None]
        return {
            "price": c[-1], "rsi10": calc_rsi(c, 10), "rsi_prev": calc_rsi(c[:-1], 10),
            "ema200": sum(c[-200:])/200 if len(c)>=200 else None,
            "bb_lo": (sum(c[-20:])/20) - 2*( (sum((x-(sum(c[-20:])/20))**2 for x in c[-20:])/20)**0.5 ),
            "poc_proxy": max(set(c[-50:]), key=c[-50:].count), "emaTrend": "alcista" if c[-1] > sum(c[-200:])/200 else "bajista"
        }
    except: return None

def score_signal(ticker, q):
    score = 0
    rsi, rsi_p = q["rsi10"], q["rsi_prev"]
    # RSI Rebote (1 pto)
    if rsi > 30 and rsi_p <= 30: score += 1
    # Sobre EMA200 (1 pto)
    epct = ((q["price"] - q["ema200"])/q["ema200"]*100) if q["ema200"] else 0
    if epct > 0: score += 1
    # Cerca de POC (1 pto)
    ppct = ((q["price"] - q["poc_proxy"])/q["poc_proxy"]*100)
    if abs(ppct) <= 2: score += 1
    # Fundamentales Excelentes (1 pto)
    fund = FUND.get(ticker, "buenos")
    if fund == "excelentes": score += 1
    # Bollinger recuperada (1 pto)
    if q["price"] > q["bb_lo"] and rsi > 30 and rsi_p <= 30: score += 1
    
    return score, epct, ppct, fund

def send_telegram(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type":"application/json"})
    try: urllib.request.urlopen(req)
    except: pass

# ── 3. EJECUCIÓN PRINCIPAL ────────────────────────────────────────────────────
all_results, signals_found, forming_found, radar_info = [], [], [], []

for ticker, sym in YF_MAP.items():
    q = fetch_ticker(sym)
    if not q: continue
    
    score, epct, ppct, fund = score_signal(ticker, q)
    all_results.append((ticker, q, score))

    if score > 2:
        signals_found.append((ticker, score, q, epct, fund))
    elif score == 2:
        forming_found.append((ticker, score, q, epct))
    elif q["rsi10"] <= 38:
        radar_info.append((ticker, q, score))
    time.sleep(0.5)

# ── 4. ENVÍO DE ALERTAS ───────────────────────────────────────────────────────
now = datetime.now().strftime("%d/%m %H:%M")

for t, s, q, e, f in signals_found:
    emoji = "🟢" if s >= 4 else "✳️"
    msg = f"{emoji} <b>SEÑAL — {t} ({s}/5)</b>\n📅 {now}\n\nRSI: {q['rsi10']}\nEMA200: {e:+.1f}%\nFund: {f}\n\n💰 <b>Sugerido: {'100%' if s>=4 else '50%'}</b>"
    send_telegram(msg)

for t, s, q, e in forming_found:
    msg = f"🟡 <b>WATCHLIST — {t} ({s}/5)</b>\n⚠️ Setup en formación.\n\nRSI: {q['rsi10']}\nEMA200: {e:+.1f}%\n\n🛑 <b>Acción:</b> NO OPERAR."
    send_telegram(msg)

if radar_info:
    radar_txt = "\n".join([f"• {t}: RSI {q['rsi10']} (Score {s}/5)" for t, q, s in radar_info[:6]])
    avg_rsi = round(sum(r[1]["rsi10"] for r in all_results)/len(all_results), 1)
    send_telegram(f"📋 <b>Reporte {now}</b>\n🌡️ RSI Promedio: {avg_rsi}\n\n<b>Radar:</b>\n{radar_txt}\n\n<i>{random.choice(BOT_NOTES)}</i>")

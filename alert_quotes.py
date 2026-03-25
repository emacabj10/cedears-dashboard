import json, urllib.request, urllib.error, time, os
from datetime import datetime

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

def calc_poc_proxy(closes):
    """Mínimo 52w × 1.15 como proxy del POC"""
    window = closes[-252:] if len(closes) >= 252 else closes
    return round(min(window) * 1.15, 2)

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
        price      = round(closes[-1], 2)
        rsi10      = calc_rsi(closes, 10)
        rsi_prev   = calc_rsi(closes[:-1], 10)
        w_closes   = [closes[i] for i in range(0, len(closes), 5)]
        rsi_w      = calc_rsi(w_closes, 10)
        ema200     = calc_ema(closes, 200)
        ema_trend  = calc_ema_trend(closes, 200)
        bb_lo      = calc_bb_lower(closes, 20, 2)
        poc_proxy  = calc_poc_proxy(closes)
        bb_recov   = (closes[-2] < bb_lo) and (price >= bb_lo) if bb_lo else False
        bb_below   = price < bb_lo if bb_lo else False
        return {
            "price":price,"rsi10":rsi10,"rsi_prev":rsi_prev,
            "rsiW":rsi_w,"ema200":ema200,"emaTrend":ema_trend,
            "bb_lo":bb_lo,"bb_recov":bb_recov,"bb_below":bb_below,
            "poc_proxy":poc_proxy,
        }
    except Exception as e:
        print(f"  Error: {e}"); return None

# ── Scoring ───────────────────────────────────────────────────────────────────
def score_signal(ticker, q):
    fund    = FUND.get(ticker, "buenos")
    fund_ex = fund == "excelentes"
    fund_ok = fund in ["excelentes","buenos"]
    price   = q["price"]
    ema200  = q["ema200"] or 1
    epct    = (price - ema200) / ema200 * 100
    rsi10   = q["rsi10"] or 50
    rsi_prev= q["rsi_prev"] or rsi10
    poc     = q["poc_proxy"] or 1
    ppct    = (price - poc) / poc * 100

    score = 0
    conds = []

    # C1: RSI(10) rebotó desde <30 (cruzó de <30 a >30)
    rsi_bounced = (rsi10 > 30 and rsi_prev <= 30)
    rsi_oversold = rsi10 <= 30
    if rsi_bounced:
        score += 1
        conds.append(("ok", f"RSI(10) {rsi10} — Rebotó (salió de oversold)"))
    elif rsi_oversold:
        conds.append(("warn", f"RSI(10) {rsi10} — En oversold, sin rebote aún"))
    else:
        conds.append(("no", f"RSI(10) {rsi10} — Fuera de zona oversold"))

    # C2: Divergencia — no detectable automáticamente, omitir score
    # C3: BB inferior recuperó
    if q["bb_recov"]:
        score += 1
        conds.append(("ok", f"BB: Recuperó banda inferior (${q['bb_lo']})"))
    elif q["bb_below"]:
        conds.append(("warn", f"BB: Precio bajo banda inferior (${q['bb_lo']}) — sin recuperación"))
    else:
        conds.append(("no", "BB: Precio dentro de bandas"))

    # C4: EMA200
    ema_trend = q["emaTrend"]
    trend_lbl = {"subiendo":"Alcista ↑","lateral":"Lateral →","bajando":"Bajista ↓"}.get(ema_trend, ema_trend)
    if epct >= 0:
        score += 1
        conds.append(("ok", f"EMA200: {epct:+.1f}% sobre la media — Tendencia {trend_lbl}"))
    elif ema_trend == "subiendo" and epct >= -5:
        conds.append(("warn", f"EMA200: {epct:+.1f}% bajo — cerca, tendencia {trend_lbl}"))
    elif ema_trend == "subiendo" and fund_ex and epct >= -20:
        conds.append(("warn", f"EMA200: {epct:+.1f}% bajo — fund. excelentes compensan"))
    else:
        conds.append(("no", f"EMA200: {epct:+.1f}% bajo la media — {trend_lbl}"))

    # C5: POC proxy
    if ppct <= -15:
        score += 1
        conds.append(("ok", f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Zona de valor fuerte"))
    elif ppct <= -5:
        conds.append(("warn", f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Cerca de zona de valor"))
    elif ppct < 0:
        conds.append(("no", f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Neutral"))
    else:
        conds.append(("no", f"POC: {ppct:.1f}% sobre (${poc:,.0f}) — Sobre valor justo"))

    # Zona máxima oportunidad
    poc_max_op = fund_ex and ppct <= -25 and ppct >= -40

    # Estado RSI para setup en formación — CORREGIDO
    # "Bajando hacia 30" = RSI entre 31-38 y viene bajando
    # "En oversold" = RSI ≤ 30
    forming = (rsi10 > 30 and rsi10 <= 38 and rsi_prev > rsi10)

    return score, conds, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Sin credenciales — imprimiendo:\n" + message); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  Telegram OK ({r.status})")
    except Exception as e:
        print(f"  Telegram error: {e}")

def ci(st):
    return {"ok":"✅","warn":"⚠️","no":"➖"}.get(st,"➖")

# ── Main ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"CEDEARS ALERTAS — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
print(f"{'='*55}\n")

signals_found  = []
forming_found  = []
all_results    = []
watchlist_info = []

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
        if ticker in existing:
            prev = existing[ticker]
            q = {
                "price":prev.get("price",0),"rsi10":prev.get("rsi10",50),
                "rsi_prev":prev.get("rsiPrev",prev.get("rsi10",50)),
                "rsiW":prev.get("rsiW",50),"ema200":prev.get("ema200",0),
                "emaTrend":prev.get("emaTrend","lateral"),
                "bb_lo":None,"bb_recov":False,"bb_below":False,
                "poc_proxy":None,
            }
            print("datos anteriores")
        else:
            print("sin datos"); continue
    else:
        print(f"RSI {q['rsi10']} · ${q['price']}")

    score, conds, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold = \
        score_signal(ticker, q)
    all_results.append((ticker, score, q, epct))

    if score >= 3:
        signals_found.append((ticker, score, conds, q, epct, ppct, fund, poc_max_op))
    elif forming:
        forming_found.append((ticker, q, epct, ppct, fund, score, conds))
    elif rsi_oversold or (q["rsi10"] and q["rsi10"] <= 40):
        watchlist_info.append((ticker, q, epct, score))

    time.sleep(0.5)

now_str  = datetime.now().strftime("%d/%m %H:%M")
date_str = datetime.now().strftime("%d/%m/%Y")

# ── 1. Señales confirmadas ────────────────────────────────────────────────────
for ticker, score, conds, q, epct, ppct, fund, poc_max_op in signals_found:
    emoji  = "🟢" if score >= 4 else "🟡"
    size   = "Posición completa (100%)" if score >= 4 else "Media posición (50%)"
    rsiw   = q.get("rsiW") or 0
    rsiw_lbl = "saludable ✓" if rsiw >= 40 else ("débil ⚠" if rsiw >= 25 else "muy bajista ✗")

    lines = [f"{ci(st)} {txt}" for st, txt in conds]
    poc_badge = ""
    if poc_max_op:
        poc_badge = f"\n⭐ <b>Zona máxima oportunidad</b> — precio {ppct:.1f}% bajo POC · fund. excelentes\n"

    msg = (
        f"{emoji} <b>SEÑAL — {ticker} ({score}/5)</b>\n"
        f"📅 {now_str} · Fundamentals: {fund}\n"
        f"{poc_badge}\n"
        + "\n".join(lines) +
        f"\n\n📈 RSI semanal: {rsiw} — {rsiw_lbl}"
        f"\n💵 Precio: ${q['price']:,}"
        f"\n\n🏷 <b>Tamaño sugerido: {size}</b>"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.3)

# ── 2. Setups en formación ────────────────────────────────────────────────────
for ticker, q, epct, ppct, fund, score, conds in forming_found:
    bb_ctx = ""
    if q.get("bb_below"):
        bb_ctx = f"\n• Se acerca a la banda inferior de Bollinger (${q['bb_lo']})"
    elif q.get("bb_recov"):
        bb_ctx = "\n• Recuperó banda inferior de Bollinger"

    msg = (
        f"⏳ <b>WATCHLIST — {ticker} ({score}/5)</b>\n"
        f"📅 {now_str}\n\n"
        f"⚠️ <b>Setup en formación:</b> RSI(10) en {q['rsi10']} y bajando hacia 30"
        f"{bb_ctx}\n"
        f"• Precio actual: ${q['price']:,}\n"
        f"• EMA200: {epct:+.1f}%\n"
        f"• Fundamentals: {fund}\n\n"
        f"👀 <b>Acción:</b> No operar aún — esperar rebote confirmado en RSI"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.3)

# ── 3. Resumen diario ─────────────────────────────────────────────────────────
# Armar lista de activos en radar (RSI ≤ 40, aunque no disparen señal)
radar_lines = []
for ticker, q, epct, score in sorted(watchlist_info, key=lambda x: x[1]["rsi10"] or 99):
    rsi = q["rsi10"] or 0
    if rsi <= 30:
        estado = "en oversold"
    elif rsi <= 35:
        estado = "muy cerca de oversold"
    else:
        estado = "acercándose a zona"
    radar_lines.append(f"• <b>{ticker}</b>: RSI(10) {rsi} — {estado} · Score {score}/5")

radar_section = ""
if radar_lines:
    radar_section = "\n\n📡 <b>En radar:</b>\n" + "\n".join(radar_lines[:5])

total_sig  = len(signals_found)
total_form = len(forming_found)

if total_sig == 0 and total_form == 0:
    intro = f"Hoy no se detectaron señales confirmadas ni setups activos."
else:
    intro = f"Se detectaron <b>{total_sig}</b> señal(es) confirmada(s) y <b>{total_form}</b> setup(s) en formación."

summary_msg = (
    f"📋 <b>Resumen de Mercado — {date_str}</b>\n\n"
    f"{intro}"
    f"{radar_section}\n\n"
    f"🔢 Tickers analizados: {len(all_results)}\n"
    f"⏰ Última actualización: {now_str}"
)
print(f"\n{summary_msg}\n")
send_telegram(summary_msg)

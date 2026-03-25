import json, urllib.request, urllib.error, time, os, random
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

BOT_NOTES = [
    "Día de paciencia. El mercado está en fase de digestión.",
    "RSI promedio en zona neutral — esperar definición.",
    "Los mejores setups suelen venir después de estas fases de compresión.",
    "Sin señales no hay operación. La paciencia es parte de la estrategia.",
    "El mejor trade a veces es no operar. Esperá el setup limpio.",
    "Zona de acumulación institucional histórica en varios activos. Atención.",
]


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

def calc_bb_upper(closes, period=20, std=2):
    if len(closes) < period: return None
    window = closes[-period:]
    mean = sum(window)/period
    variance = sum((x-mean)**2 for x in window)/period
    return round(mean + std*(variance**0.5), 2)

def calc_bb_width(closes, period=20, std=2):
    """Ancho relativo de las BB — para detectar squeeze"""
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
        # bb_lo_prev: banda inferior calculada con los cierres hasta ayer
        bb_lo_prev = calc_bb_lower(closes[:-1], 20, 2)
        bb_hi     = calc_bb_upper(closes, 20, 2)
        bb_wid    = calc_bb_width(closes, 20, 2)
        poc_proxy = calc_poc_proxy(closes)
        price_prev = closes[-2] if len(closes) >= 2 else price

        # Rebote Bollinger confirmado: ayer cerró por debajo, hoy cerró por encima
        bb_recov   = (bb_lo_prev is not None and price_prev <= bb_lo_prev and price >= bb_lo) if bb_lo else False
        bb_below   = price < bb_lo if bb_lo else False
        bb_above   = price > bb_hi if bb_hi else False
        bb_squeeze = (bb_wid[0] < bb_wid[1] * 0.85) if bb_wid else False
        bb_near_lo = (not bb_below) and bb_lo and ((price - bb_lo) / bb_lo * 100 < 2)

        # Divergencia alcista: precio hace mínimo más bajo, RSI hace mínimo más alto
        div_bullish = False
        if rsi10 is not None and rsi_prev is not None:
            div_bullish = (price < price_prev) and (rsi10 > rsi_prev)

        return {
            "price":price,"rsi10":rsi10,"rsi_prev":rsi_prev,
            "rsiW":rsi_w,"ema200":ema200,"emaTrend":ema_trend,
            "bb_lo":bb_lo,"bb_hi":bb_hi,"bb_recov":bb_recov,
            "bb_below":bb_below,"bb_above":bb_above,
            "bb_squeeze":bb_squeeze,"bb_near_lo":bb_near_lo,
            "poc_proxy":poc_proxy,
            "div_bullish": div_bullish,
            "price_prev": price_prev,
            "bb_lo_prev": bb_lo_prev,
        }
    except Exception as e:
        print(f"  Error: {e}"); return None

# ── Labels por indicador ──────────────────────────────────────────────────────

def rsi_label_signal(rsi10, rsi_prev):
    """Labels RSI para señal confirmada"""
    if rsi10 > 30 and rsi_prev <= 30:
        return f"RSI(10): {rsi10} — Rebotó (Cruzó de <30 a >30)"
    elif rsi10 <= 30:
        return f"RSI(10): {rsi10} — En Oversold (Bajo 30, sin rebote)"
    elif rsi10 >= 70:
        return f"RSI(10): {rsi10} — Overbought (Sobre 70, posible techo)"
    elif rsi10 > 30 and rsi_prev and rsi_prev > rsi10:
        return f"RSI(10): {rsi10} — Bajando hacia 30 (Debilitamiento)"
    else:
        return f"RSI(10): {rsi10} — Zona Neutral (Sin dirección clara)"

def rsi_label_watchlist(rsi10, rsi_prev):
    """Labels RSI para watchlist/setup en formación"""
    if rsi10 <= 30:
        return f"RSI(10): {rsi10} — En Oversold (Bajo 30, sin rebote confirmado aún)"
    elif rsi10 <= 35 and rsi_prev and rsi_prev > rsi10:
        return f"RSI(10): {rsi10} — Bajando hacia 30 (Sin fuerza de rebote)"
    elif rsi10 <= 38:
        return f"RSI(10): {rsi10} — Cerca de Oversold (Preparando posible entrada)"
    elif rsi_prev and rsi_prev < rsi10 and rsi10 <= 45:
        return f"RSI(10): {rsi10} — Marcando mínimos más altos (Atención a posible giro)"
    else:
        return f"RSI(10): {rsi10} — Consolidando en zona neutral"

def ema_label_signal(epct, ema_trend, ema200):
    """Labels EMA200 para señal confirmada"""
    if epct >= 0:
        return f"EMA200: +{epct:.1f}% sobre la media — Tendencia Alcista (Soporte dinámico)"
    elif abs(epct) <= 3:
        return f"EMA200: {epct:.1f}% — Testeando EMA200 (Zona crítica de decisión)"
    elif epct < 0 and ema_trend == "subiendo":
        return f"EMA200: {epct:.1f}% — Precio recuperando tendencia de largo plazo"
    else:
        return f"EMA200: {epct:.1f}% bajo la media — Tendencia Bajista (Resistencia dinámica)"

def ema_label_watchlist(epct, ema_trend):
    """Labels EMA200 para watchlist"""
    if epct >= 0 and epct <= 5:
        return f"EMA200: +{epct:.1f}% — Precio buscando soporte en la media de 200"
    elif epct >= 0 and epct > 5:
        return f"EMA200: +{epct:.1f}% — Extendida (Buscando corrección técnica hacia la media)"
    elif abs(epct) <= 3:
        return f"EMA200: {epct:.1f}% — Testeando rotura (Precaución: cambio de tendencia)"
    else:
        return f"EMA200: {epct:.1f}% — Bajo la media (Resistencia dinámica activa)"

def poc_label_signal(ppct, poc):
    """Labels POC para señal confirmada"""
    if ppct <= -25:
        return f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Máxima oportunidad (Desviación importante del valor real)"
    elif ppct <= -15:
        return f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Zona de Valor (Precio \"barato\")"
    elif ppct <= -5:
        return f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Cerca de zona de valor"
    elif abs(ppct) <= 2:
        return f"POC: ${poc:,.0f} — En Punto de Equilibrio (Alta liquidez)"
    else:
        return f"POC: +{ppct:.1f}% sobre (${poc:,.0f}) — Extendiendo sobre valor (Posible toma de ganancias)"

def poc_label_watchlist(ppct, poc, price):
    """Labels POC para watchlist"""
    if ppct <= -10:
        return f"POC: -{abs(ppct):.1f}% — Subvaluada respecto al perfil de volumen (Oportunidad en desarrollo)"
    elif ppct <= -2:
        return f"POC: ${poc:,.0f} — Precio actual ${price:,} (Regresando a zona de alta liquidez)"
    elif abs(ppct) <= 2:
        return f"POC: ${poc:,.0f} — Intentando hacer pie en el volumen máximo"
    else:
        return f"POC: +{ppct:.1f}% sobre (${poc:,.0f}) — Sobre valor justo"

def bb_label_signal(q):
    """Labels BB para señal confirmada"""
    if q.get("bb_recov"):
        return "BB: Recuperó banda inferior (Rebote Bollinger confirmado ✅)"
    elif q.get("bb_squeeze"):
        return "BB: Bandas comprimidas (Explosión de volatilidad inminente)"
    elif q.get("bb_above"):
        return "BB: Fuera de banda superior (Sobrecomprado en el corto plazo)"
    elif q.get("bb_near_lo"):
        return f"BB: Apoyando en banda inferior (Rebote técnico probable)"
    else:
        return "BB: Precio dentro de bandas"

def bb_label_watchlist(q):
    """Labels BB para watchlist"""
    if q.get("bb_below"):
        return "BB: Velas cerrando fuera de la banda (Extremo de pánico)"
    elif q.get("bb_near_lo"):
        return "BB: Presionando banda inferior (Posible zona de capitulación)"
    elif q.get("bb_squeeze"):
        return "BB: Compresión de volatilidad (Esperando ruptura de rango)"
    else:
        return "BB: Precio dentro de bandas"

def sugerencia_signal(score, rsi10, epct, ppct):
    if score >= 4:
        return "Señal fuerte. Entrada con posición completa según tu plan."
    elif score == 3 and ppct <= -15:
        return "Setup sólido en zona de valor. Media posición — esperar confirmación de vela."
    elif score == 3:
        return "Setup válido. Media posición. Chequeá BB y divergencias en TradingView antes de entrar."
    else:
        return "Señal débil. Monitorear — no operar aún."

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
    tags  = []

    rsi_bounced  = (rsi10 > 30 and rsi_prev <= 30)
    rsi_oversold = rsi10 <= 30

    # ── Puntos base ──────────────────────────────────────────────────────────
    if rsi_bounced:
        score += 1

    # Rebote Bollinger confirmado (+1 punto)
    if q.get("bb_recov"):
        score += 1
        tags.append("Rebote Bollinger ✅")

    # Divergencia alcista (+1 punto)
    if q.get("div_bullish"):
        score += 1
        tags.append("Divergencia Alcista 📐")

    if epct >= 0:
        score += 1
    elif ema_trend_ok(q["emaTrend"], epct, fund_ex, fund_ok):
        pass

    # POC: precio con descuento moderado (-5%) o más = condición de calidad
    if ppct <= -5:
        score += 1

    poc_max_op = fund_ex and ppct <= -25 and ppct >= -40

    # Setup en formación: cualquier RSI ≤ 38 sin rebote confirmado es watchlist
    forming_rsi_zone  = (rsi10 <= 38 and not rsi_bounced)
    forming_oversold  = (rsi10 <= 30 and not rsi_bounced)
    forming = forming_rsi_zone or forming_oversold  # forming_rsi_zone ya lo cubre todo

    # ── Limpieza del Radar ────────────────────────────────────────────────────
    # Si RSI superó 42, ya no está "frío": sale del radar automáticamente
    # (simplemente no lo marcamos como radar_candidate desde score_signal;
    #  la lógica de exclusión se aplica en el loop principal)

    return score, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold, tags

def ema_trend_ok(trend, epct, fund_ex, fund_ok):
    if epct >= 0: return True
    if trend == "subiendo" and epct >= -5: return True
    if trend == "subiendo" and fund_ex and epct >= -20: return True
    return False

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Sin credenciales:\n" + message); return
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

# ── Main ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"CEDEARS ALERTAS — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
print(f"{'='*55}\n")

signals_found  = []   # score >= 3  → alerta verde individual
watchlist_found = []  # score == 2  → alerta amarilla individual
radar_info     = []   # score 0-1   → solo en reporte de cierre
all_results    = []

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
                "rsi_prev":prev.get("rsi10",50),  # igual al actual → nunca genera rsi_bounced
                "rsiW":prev.get("rsiW",50),"ema200":prev.get("ema200",0),
                "emaTrend":prev.get("emaTrend","lateral"),
                "bb_lo":None,"bb_hi":None,"bb_recov":False,
                "bb_below":False,"bb_above":False,"bb_squeeze":False,
                "bb_near_lo":False,"poc_proxy":None,
                "div_bullish":False,"price_prev":0,"bb_lo_prev":None,
                "_fallback":True,
            }
            print("datos anteriores")
        else:
            print("sin datos"); continue
    else:
        div_tag = " · DIV✅" if q.get("div_bullish") else ""
        bb_tag  = " · BB↑"   if q.get("bb_recov")   else ""
        print(f"RSI {q['rsi10']} · ${q['price']}{div_tag}{bb_tag}")

    if q.get("_fallback"):
        # Datos del caché — no generan señales ni watchlists, solo radar si aplica
        rsi10 = q["rsi10"] or 50
        _, _, epct, ppct, _, _, _, _, tags = score_signal(ticker, q)
        all_results.append((ticker, 0, q, epct, ppct))
        if rsi10 <= 38:
            radar_info.append((ticker, q, epct, ppct, 0, tags))
        continue

    score, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold, tags = \
        score_signal(ticker, q)
    all_results.append((ticker, score, q, epct, ppct))

    rsi10 = q["rsi10"] or 50

    if rsi_bounced and rsi10 > 30 and score >= 3:
        # ✅ Señal verde: RSI cruzó 30 hacia arriba (está HOY sobre 30) Y score alto
        print(f"  >>> SEÑAL CONFIRMADA: {ticker} score={score} rsi={rsi10} rsi_prev={q.get('rsi_prev')}")
        signals_found.append((ticker, score, q, epct, ppct, fund, poc_max_op, tags))
    elif rsi10 <= 38:
        # RSI en zona fría (≤38) → watchlist si score≥2, radar si score≤1
        if score >= 2:
            watchlist_found.append((ticker, score, q, epct, ppct, tags))
        else:
            radar_info.append((ticker, q, epct, ppct, score, tags))

    time.sleep(0.5)

# Watchlists ordenadas por RSI ascendente (más cerca del oversold primero)
watchlist_found.sort(key=lambda x: x[2]["rsi10"] or 99)

now_str  = datetime.now().strftime("%d/%m %H:%M")
date_str = datetime.now().strftime("%d/%m/%Y")

# Encabezado dinámico según hora de activación
_hour = datetime.now().hour
if 9 <= _hour < 13:
    session_header = f"🔔 APERTURA DE MERCADO — {datetime.now().strftime('%H:%M')}\nIniciando reporte técnico..."
elif 16 <= _hour < 20:
    session_header = f"🔔 CIERRE DE MERCADO — {datetime.now().strftime('%H:%M')}\nIniciando reporte técnico..."
else:
    session_header = f"🔔 REPORTE DE MERCADO — {datetime.now().strftime('%H:%M')}\nIniciando análisis técnico..."

send_telegram(session_header)
time.sleep(0.3)

# ── 1. Señales confirmadas (Score 3/4/5) → alerta verde individual ────────────
for ticker, score, q, epct, ppct, fund, poc_max_op, tags in signals_found:
    rsi10  = q["rsi10"] or 50
    rsi_p  = q["rsi_prev"] or rsi10
    poc    = q["poc_proxy"] or 0

    poc_badge = ""
    if poc_max_op:
        poc_badge = f"\n⭐ <b>Máxima oportunidad</b> — {ppct:.1f}% bajo POC · Fundamentals excelentes\n"

    sugerencia = sugerencia_signal(score, rsi10, epct, ppct)

    # Tags de divergencia y rebote Bollinger
    tags_line = ""
    if tags:
        tags_line = "\n🏷 <b>Tags:</b> " + " | ".join(tags) + "\n"

    msg = (
        f"🟢 <b>{ticker} — SEÑAL {score}/5</b>\n"
        f"{poc_badge}"
        f"\n<b>📊 Indicadores</b>\n"
        f"📉 {rsi_label_signal(rsi10, rsi_p)}\n"
        f"📈 {ema_label_signal(epct, q['emaTrend'], q['ema200'])}\n"
        f"📦 {poc_label_signal(ppct, poc)}\n"
        f"🎢 {bb_label_signal(q)}\n"
        f"{tags_line}"
        f"\n<b>💡 Sugerencia</b>\n"
        f"{sugerencia}"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.3)

# ── 2. Watchlist — Score 2 → alerta amarilla individual ──────────────────────
for ticker, score, q, epct, ppct, tags in watchlist_found:
    rsi10 = q["rsi10"] or 50
    rsi_p = q["rsi_prev"] or rsi10
    poc   = q["poc_proxy"] or 0

    tags_line = ""
    if tags:
        tags_line = "\n🏷 <b>Tags:</b> " + " | ".join(tags) + "\n"

    msg = (
        f"🟡 <b>{ticker} — WATCHLIST {score}/5</b>\n"
        f"⚠️ <b>Estado:</b> Setup en formación. Aviso previo — monitorear.\n"
        f"\n<b>📊 Indicadores</b>\n"
        f"📉 {rsi_label_watchlist(rsi10, rsi_p)}\n"
        f"📈 {ema_label_watchlist(epct, q['emaTrend'])}\n"
        f"📦 {poc_label_watchlist(ppct, poc, q['price'])}\n"
        f"🎢 {bb_label_watchlist(q)}\n"
        f"{tags_line}"
        f"\n<b>🛑 Acción sugerida</b>\n"
        f"NO OPERAR. Esperá que el RSI cruce al alza el nivel de 30 "
        f"o validación de soporte en el POC."
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.5)

# ── 3. Resumen / Reporte de cierre ────────────────────────────────────────────
total_sig   = len(signals_found)
total_watch = len(watchlist_found)

if total_sig == 0 and total_watch == 0:
    intro = "Hoy no se detectaron señales ni watchlists activas."
else:
    parts = []
    if total_sig:   parts.append(f"<b>{total_sig}</b> señal(es) confirmada(s) 🟢")
    if total_watch: parts.append(f"<b>{total_watch}</b> watchlist(s) enviada(s) 🟡")
    intro = " · ".join(parts) + "."

# Radar: score 0-1, RSI ≤ 42 — solo en reporte de cierre, sin alertas individuales
radar_lines = []
radar_filtered = [(t, q, ep, pp, sc, tgs) for t, q, ep, pp, sc, tgs in radar_info
                  if (q["rsi10"] or 99) <= 42]
for ticker, q, epct, ppct, score, tags in sorted(radar_filtered, key=lambda x: x[1]["rsi10"] or 99)[:6]:
    rsi = q["rsi10"] or 0
    line = f"• <b>{ticker}</b>: RSI(10) {rsi}"
    if rsi <= 35:
        line += " — bajando hacia 30."
    elif abs(epct) <= 3:
        line += " — cerca de testear la EMA200."
    else:
        line += "."
    if q.get("bb_below"):
        line += " Perdió banda inferior Bollinger."
        if ppct <= -5 and q.get("poc_proxy"):
            line += f" POC {abs(ppct):.0f}% abajo (${q['poc_proxy']:,.0f})."
        line += " Sin rebote confirmado."
    elif abs(ppct) <= 3 and q.get("poc_proxy"):
        line += " Consolidando sobre el POC."
    if tags:
        line += " [" + ", ".join(tags) + "]"
    if score > 0:
        line += f" Score: {score}/5."
    radar_lines.append(line)

radar_section = ""
if radar_lines:
    radar_section = "\n\n<b>📡 Activos bajo confirmación:</b>\n" + "\n".join(radar_lines)

rsi_values = [q["rsi10"] for _, _, q, _, _ in all_results if q.get("rsi10")]
avg_rsi = round(sum(rsi_values)/len(rsi_values), 1) if rsi_values else 50
if avg_rsi < 30:
    bot_note = f"RSI promedio del panel {avg_rsi} — mercado en oversold generalizado. Momento de máxima atención."
elif avg_rsi < 40:
    bot_note = f"RSI promedio del panel {avg_rsi} — mercado en zona de debilidad. Los setups están madurando."
elif avg_rsi > 65:
    bot_note = f"RSI promedio del panel {avg_rsi} — mercado sobrecomprado. No es zona de entrada, esperá corrección."
else:
    bot_note = random.choice(BOT_NOTES)

summary_msg = (
    f"📅 <b>Resumen Diario — {date_str}</b>\n\n"
    f"{intro}"
    f"{radar_section}\n\n"
    f"💡 <b>Nota del Bot:</b> {bot_note}"
)
print(f"\n{summary_msg}\n")
send_telegram(summary_msg)

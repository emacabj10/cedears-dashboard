import json, urllib.request, urllib.error, time, os, random
from datetime import datetime, timezone, timedelta

# Hora Argentina (UTC-3)
ARG_TZ = timezone(timedelta(hours=-3))
def now_arg():
    return datetime.now(ARG_TZ)

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

# Mapa TradingView: símbolo exacto para la URL del gráfico
TV_MAP = {
    "MSFT":"NASDAQ:MSFT","GOOGL":"NASDAQ:GOOGL","AMZN":"NASDAQ:AMZN",
    "META":"NASDAQ:META","BRK.B":"NYSE:BRK.B","V":"NYSE:V",
    "WMT":"NYSE:WMT","MELI":"NASDAQ:MELI","QQQ":"NASDAQ:QQQ",
    "SPY":"AMEX:SPY","DIA":"AMEX:DIA","AMD":"NASDAQ:AMD",
    "KO":"NYSE:KO","PEP":"NASDAQ:PEP","MCD":"NYSE:MCD",
    "BABA":"NYSE:BABA","PYPL":"NASDAQ:PYPL","TSLA":"NASDAQ:TSLA",
    "GLD":"AMEX:GLD","BTC":"BINANCE:BTCUSDT","ETH":"BINANCE:ETHUSDT",
    "BNB":"BINANCE:BNBUSDT",
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
    # 2y para que la EMA200 tenga suficiente historial y sea precisa
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2y"
    headers = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) < 210: return None  # mínimo 210 para EMA200 confiable
        price     = round(closes[-1], 2)
        rsi10     = calc_rsi(closes, 10)
        rsi_prev  = calc_rsi(closes[:-1], 10)
        w_closes  = [closes[i] for i in range(0, len(closes), 5)]
        rsi_w     = calc_rsi(w_closes, 10)
        ema200    = calc_ema(closes, 200)
        ema_trend = calc_ema_trend(closes, 200)
        bb_lo     = calc_bb_lower(closes, 20, 2)
        bb_lo_prev = calc_bb_lower(closes[:-1], 20, 2)
        bb_hi     = calc_bb_upper(closes, 20, 2)
        bb_wid    = calc_bb_width(closes, 20, 2)
        poc_proxy = calc_poc_proxy(closes)
        price_prev = closes[-2] if len(closes) >= 2 else price

        # Rebote Bollinger confirmado:
        # ayer cerró ESTRICTAMENTE debajo de la banda, hoy cerró encima o en ella
        bb_recov   = (
            bb_lo_prev is not None
            and price_prev < bb_lo_prev   # estricto: debajo de banda ayer
            and bb_lo is not None
            and price >= bb_lo            # hoy recuperó la banda
        ) if bb_lo else False
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
        return f"RSI(10): {rsi10} — Rebotó (Cruzó de 30)"
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
        return "BB: Recuperó banda inferior (Rebote Bollinger confirmado)"
    elif q.get("bb_squeeze"):
        return "BB: Bandas comprimidas (Explosión de volatilidad inminente)"
    elif q.get("bb_above"):
        return "BB: Fuera de banda superior (Sobrecomprado en el corto plazo)"
    elif q.get("bb_near_lo"):
        return "BB: Apoyando en banda inferior (Rebote técnico probable)"
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

def generar_analisis(ticker, score, q, epct, ppct, fund):
    """
    Análisis contextual de 2-3 líneas:
      Línea 1 — Contexto de mercado (tendencia, corrección, lateralización)
      Línea 2 — Niveles clave BB y EMA (sin POC — referencia visual solamente)
      Línea 3 — Divergencias y momentum (solo si hay señal real)
    """
    rsi10     = q.get("rsi10") or 50
    rsi_prev  = q.get("rsi_prev") or rsi10
    ema_trend = q.get("emaTrend") or "lateral"
    div       = q.get("div_bullish", False)
    bb_recov  = q.get("bb_recov", False)
    bb_below  = q.get("bb_below", False)
    bb_near   = q.get("bb_near_lo", False)

    lineas = []

    # ── Línea 1: Contexto de mercado ─────────────────────────────────────────
    if epct >= 0 and ema_trend == "subiendo":
        ctx = f"Tendencia alcista de largo plazo intacta — precio {epct:.1f}% sobre EMA200 en ascenso. Corrección técnica dentro de estructura positiva."
    elif epct >= 0 and ema_trend == "lateral":
        ctx = f"Mercado lateralizando — precio {epct:.1f}% sobre EMA200 sin tendencia definida. La corrección actual busca soporte en la media."
    elif epct >= 0 and ema_trend == "bajando":
        ctx = f"EMA200 perdiendo pendiente con precio aún {epct:.1f}% sobre la media — señal de agotamiento de tendencia alcista. Corrección en desarrollo."
    elif epct >= -3:
        ctx = f"Precio testeando la EMA200 ({epct:.1f}%) — zona de decisión crítica. Un cierre por encima confirma el soporte dinámico."
    elif epct >= -10:
        ctx = f"Corrección moderada — precio {abs(epct):.1f}% bajo EMA200. La media actúa como resistencia dinámica en el corto plazo."
    else:
        ctx = f"Corrección profunda — precio {abs(epct):.1f}% bajo EMA200. Zona de capitulación con tendencia bajista de corto plazo vigente."
    lineas.append(ctx)

    # ── Línea 2: Estructura de precio — BB ───────────────────────────────────
    if bb_recov and epct >= 0:
        niv = "Recuperó banda inferior de BB con precio sobre EMA200 — doble confluencia técnica alcista. Rebote confirmado."
    elif bb_recov and epct >= -3:
        niv = "Recuperó banda inferior de BB testeando la EMA200 — rebote técnico en zona de soporte dinámico."
    elif bb_recov:
        niv = f"Recuperó banda inferior de BB con precio {abs(epct):.1f}% bajo EMA200 — rebote técnico en corrección profunda."
    elif bb_below:
        niv = "Precio fuera de la banda inferior de BB — extremo de volatilidad bajista. Sin rebote confirmado aún."
    elif bb_near:
        niv = "Apoyando en banda inferior de BB sin perderla — zona de posible capitulación y rebote técnico."
    elif epct >= 0:
        niv = f"Precio {epct:.1f}% sobre EMA200 dentro de bandas — estructura técnica positiva de largo plazo."
    else:
        niv = f"Precio {abs(epct):.1f}% bajo EMA200 dentro de bandas — corrección en curso sin señales de capitulación."
    lineas.append(niv)

    # ── Línea 3: Divergencias y momentum ─────────────────────────────────────
    if div:
        lineas.append(f"Divergencia alcista confirmada — RSI({rsi10}) marcando mínimo más alto mientras el precio hace mínimo más bajo. Cambio de momentum favorable.")
    elif rsi10 > 30 and rsi_prev <= 30:
        lineas.append(f"RSI cruzó al alza el nivel 30 (de {rsi_prev} a {rsi10}) — momentum girando a favor del comprador.")
    elif rsi10 <= 28:
        lineas.append(f"RSI en oversold extremo ({rsi10}) — presión vendedora en máximos, históricamente precede rebotes técnicos.")
    elif rsi10 <= 32 and rsi10 > rsi_prev:
        lineas.append(f"RSI en {rsi10} con pendiente alcista desde {rsi_prev} — momentum comenzando a recuperarse desde zona de suelo.")

    return "\n".join(lineas)


def sugerencia_signal(score, rsi10, epct, fund, div, bb_recov):
    """
    Sugerencia para SEÑAL 3/3. Estrategia de acumulación a largo plazo.
    Entrada completa cuando hay confluencia técnica sólida.
    Media posición cuando opera contra la tendencia de fondo.
    """
    if score != 3:
        return "Señal incompleta. Monitorear — no operar aún."

    # Entrada completa: divergencia alcista + soporte técnico completo
    if div and epct >= -3:
        return (
            "Setup de alta calidad: divergencia alcista confirmada con soporte técnico completo. "
            "Entrada con posición completa. "
            "La divergencia sugiere agotamiento vendedor — favorable para acumulación de largo plazo."
        )

    # Entrada completa: sobre EMA200 + BB recuperado (setup limpio)
    if epct >= 0 and bb_recov:
        return (
            "Setup limpio: RSI rebotó, precio sobre EMA200 y recuperó banda BB. "
            "Entrada con posición completa. "
            "La EMA200 actúa como soporte dinámico de largo plazo — estructura favorable para acumulación."
        )

    # Entrada completa: testeando EMA200 como soporte + BB recuperado
    if epct >= -3 and bb_recov:
        return (
            "Rebote desde BB con precio en soporte dinámico (EMA200). "
            "Entrada con posición completa. "
            "Zona de máxima confluencia técnica — favorable para acumulación de largo plazo."
        )

    # Media posición: corrección profunda bajo EMA200
    if epct < -10:
        return (
            f"Rebote técnico con precio {abs(epct):.1f}% bajo EMA200 — tendencia bajista de corto plazo vigente. "
            "Entrada con media posición. "
            "Acumulación escalonada: ampliá si el precio confirma soporte en las próximas ruedas."
        )

    # Media posición: corrección moderada bajo EMA200
    if epct < -3:
        return (
            f"Precio en corrección moderada ({abs(epct):.1f}% bajo EMA200) — la media actúa como resistencia dinámica. "
            "Entrada con media posición. "
            "Ampliá a posición completa si el precio recupera la EMA200 con volumen."
        )

    # Default: señal técnica completa, contexto neutro
    return (
        "Setup técnico completo. "
        "Entrada con media posición — confirmá tendencia en TradingView antes de ejecutar. "
        "Ampliá a posición completa si la siguiente vela confirma continuidad alcista."
    )


def sugerencia_watchlist(score, rsi10, epct, fund, div, bb_recov, bb_below, rsi_bounced):
    """
    Sugerencia para WATCHLIST 2/3. Estrategia de acumulación a largo plazo.
    Siempre indica esperar, pero describe exactamente qué falta y qué vigilar.
    """
    ema_ok = epct >= -3
    rsi_ok = rsi_bounced
    bb_ok  = bb_recov

    # Caso 1: EMA + BB confirmados, falta RSI
    if ema_ok and bb_ok and not rsi_ok:
        if rsi10 <= 30:
            return (
                "Esperá el cruce del RSI sobre 30 para confirmar la entrada. "
                f"RSI en {rsi10} — en oversold pero sin rebote confirmado aún. "
                "Cuando cruce, los 3 puntos estarán completos: entrada con posición completa."
            )
        else:
            return (
                "EMA200 y BB recuperados — dos de tres puntos confirmados. "
                f"RSI en {rsi10}, aún no bajó a oversold. Esperá que baje y rebote sobre 30. "
                "El setup puede madurar en las próximas ruedas."
            )

    # Caso 2: RSI + EMA confirmados, falta BB
    if rsi_ok and ema_ok and not bb_ok:
        if bb_below:
            return (
                "RSI rebotó y precio sobre EMA200, pero el precio sigue fuera de la banda inferior de BB. "
                "Esperá que cierre dentro de las bandas — es la confirmación que falta. "
                "Cuando BB se recupere, setup completo: entrada con posición completa."
            )
        else:
            return (
                "RSI rebotó y precio sobre EMA200. Falta el rebote desde la banda inferior de BB. "
                "El precio aún no tocó la banda — monitorear. "
                "Si en las próximas ruedas presiona BB y rebota, setup completo."
            )

    # Caso 3: RSI + BB confirmados, falta EMA (precio bajo la media)
    if rsi_ok and bb_ok and not ema_ok:
        return (
            f"RSI y BB confirmados, pero precio {abs(epct):.1f}% bajo EMA200 — opera contra la tendencia de largo plazo. "
            "Cuando complete la señal, entrada con media posición (acumulación escalonada). "
            "Ampliá a posición completa si el precio recupera la EMA200."
        )

    # Caso 4: divergencia activa → prioridad máxima
    if div:
        falta = "RSI" if not rsi_ok else ("BB" if not bb_ok else "EMA")
        return (
            "Divergencia alcista activa — setup de alta prioridad para acumulación. "
            f"Falta confirmar {falta} para completar la señal. "
            "Monitorear de cerca: cuando se complete, entrada con posición completa."
        )

    # Caso 5: RSI cerca de oversold, setup madurando
    if rsi10 <= 35:
        return (
            f"Setup en formación con RSI en {rsi10} aproximándose a oversold. "
            "Esperá las confirmaciones técnicas faltantes antes de entrar. "
            "Si completa los 3 puntos desde esta zona, será entrada de acumulación de alta calidad."
        )

    # Default
    return (
        "Setup en formación — falta al menos una confirmación técnica para entrar. "
        "Cuando los 3 puntos estén completos, entrada según el contexto de precio. "
        "Paciencia: los mejores setups de acumulación se confirman, no se anticipan."
    )

# ── Scoring — NUEVO SISTEMA 3/3 ───────────────────────────────────────────────
def score_signal(ticker, q):
    """
    Nuevo sistema de score máximo 3 puntos:
      Punto 1 (RSI)       : rsi10 cruzando al alza el nivel de 30
                            (rsi_prev <= 30 y rsi10 > 30)
      Punto 2 (EMA200)    : precio >= ema200  O  precio a no más del 3% por debajo
      Punto 3 (Bollinger) : cierre anterior < bb_lo_prev y cierre actual >= bb_lo
                            (recuperó la banda inferior)

    POC, divergencias y fundamentals NO suman puntos pero siguen apareciendo
    en los mensajes de Telegram como indicadores de contexto.
    """
    fund    = FUND.get(ticker, "buenos")
    fund_ex = fund == "excelentes"
    price   = q["price"]
    ema200  = q["ema200"] or 1
    epct    = (price - ema200) / ema200 * 100
    rsi10   = q["rsi10"] or 50
    rsi_prev= q["rsi_prev"] or rsi10
    poc     = q["poc_proxy"] or 1
    ppct    = (price - poc) / poc * 100

    score = 0

    # ── Punto 1: RSI cruzando al alza el nivel de 30 ─────────────────────────
    rsi_bounced  = (rsi10 > 30 and rsi_prev <= 30)
    rsi_oversold = rsi10 <= 30

    if rsi_bounced:
        score += 1

    # ── Punto 2: EMA200 — precio encima O a no más del 3% por debajo ────────
    ema_ok = epct >= -3
    if ema_ok:
        score += 1

    # ── Punto 3: Bollinger — recuperó banda inferior ──────────────────────────
    if q.get("bb_recov"):
        score += 1

    # Setup en formación: RSI ≤ 38 sin rebote confirmado
    forming_rsi_zone = (rsi10 <= 38 and not rsi_bounced)
    forming = forming_rsi_zone

    return score, forming, epct, ppct, fund, rsi_bounced, rsi_oversold

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Sin credenciales:\n" + message); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Intento 1: con HTML
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
            return
    except Exception as e:
        print(f"  Telegram HTML error: {e}")
        print(f"  MSG DUMP: {repr(message[:300])}")

    # Intento 2: sin parse_mode (texto plano, borra tags HTML)
    import re
    plain = re.sub(r"<[^>]+>", "", message)
    payload2 = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": plain,
    }).encode()
    req2 = urllib.request.Request(url, data=payload2,
                                  headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req2, timeout=10) as r:
            print(f"  Telegram OK plain ({r.status})")
    except Exception as e:
        print(f"  Telegram plain error: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"CEDEARS ALERTAS — {now_arg().strftime('%d/%m/%Y %H:%M')} (ARG)")
print(f"{'='*55}\n")

signals_found   = []   # score 3/3  → alerta verde individual
watchlist_found = []   # score 2/3  → alerta amarilla individual
radar_info      = []   # score 0-1  → solo en reporte de cierre
all_results     = []

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
                "rsi_prev":prev.get("rsi10",50),
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
        ema200_val = q.get("ema200") or 0
        epct_debug = (q["price"] - ema200_val) / ema200_val * 100 if ema200_val else 0
        print(f"RSI {q['rsi10']} · ${q['price']} · EMA200=${ema200_val} ({epct_debug:+.1f}%){div_tag}{bb_tag}")

    if q.get("_fallback"):
        rsi10 = q["rsi10"] or 50
        _, _, epct, ppct, _, _, _ = score_signal(ticker, q)
        all_results.append((ticker, 0, q, epct, ppct))
        if rsi10 <= 38:
            radar_info.append((ticker, q, epct, ppct, 0))
        continue

    score, forming, epct, ppct, fund, rsi_bounced, rsi_oversold = \
        score_signal(ticker, q)
    all_results.append((ticker, score, q, epct, ppct))

    rsi10 = q["rsi10"] or 50

    # Watchlist por BB recuperado + EMA ok (aunque RSI no llegó a 30)
    bb_ema_watchlist = (
        q.get("bb_recov", False)
        and epct >= -3
        and not rsi_bounced
        and score >= 2
    )

    if score == 3 and rsi_bounced:
        print(f"  >>> SEÑAL 3/3: {ticker} rsi={rsi10} rsi_prev={q.get('rsi_prev')} bb_recov={q.get('bb_recov')} epct={epct:.1f}")
        signals_found.append((ticker, score, q, epct, ppct, fund))
    elif (score == 2 and not rsi_bounced and rsi10 <= 45) or bb_ema_watchlist:
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → watchlist (bb_ema={bb_ema_watchlist})")
        watchlist_found.append((ticker, score, q, epct, ppct))
    elif (rsi10 <= 35) or (rsi10 < 30 and not rsi_bounced) or (abs(epct) <= 1):
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → radar")
        radar_info.append((ticker, q, epct, ppct, score))
    else:
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → ignorado")

    time.sleep(0.5)

# Watchlists ordenadas por RSI ascendente
watchlist_found.sort(key=lambda x: x[2]["rsi10"] or 99)

now_str  = now_arg().strftime("%d/%m %H:%M")
date_str = now_arg().strftime("%d/%m/%Y")

# Sesión según hora Argentina
_hour = now_arg().hour
if 9 <= _hour < 13:
    session_name = "APERTURA DE MERCADO"
    is_cierre    = False
elif 13 <= _hour < 16:
    session_name = "MEDIA RUEDA DE MERCADO"
    is_cierre    = False
else:
    session_name = "CIERRE DE MERCADO"
    is_cierre    = True

session_header = (
    f"🔔 {session_name} — {now_arg().strftime('%H:%M')}\n"
    f"Iniciando reporte técnico..."
)

# ── Persistencia de alertas del día en data.json ─────────────────────────────
# Lee acumulado del día; resetea si cambió la fecha
_today = now_arg().strftime("%Y-%m-%d")
_daily = {"date": _today, "signals": [], "watchlist": []}
try:
    with open("data.json", "r") as f:
        _dj = json.load(f)
    if _dj.get("daily", {}).get("date") == _today:
        _daily = _dj["daily"]
except Exception:
    pass

# ── 1. Señales confirmadas (Score 3/3) → alerta verde individual ──────────────
_header_sent = False

for ticker, score, q, epct, ppct, fund in signals_found:
    rsi10  = q["rsi10"] or 50
    rsi_p  = q["rsi_prev"] or rsi10
    poc    = q["poc_proxy"] or 0
    div    = q.get("div_bullish", False)
    bb_rec = q.get("bb_recov", False)

    sugerencia = sugerencia_signal(score, rsi10, epct, fund, div, bb_rec)
    analisis   = generar_analisis(ticker, score, q, epct, ppct, fund)

    _tv_sym  = TV_MAP.get(ticker, ticker)
    _link_tv = f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym}">Ver gráfico en TradingView →</a>'

    if not _header_sent:
        send_telegram(session_header)
        time.sleep(0.3)
        _header_sent = True

    msg = (
        f"🟢 <b>{ticker} — SEÑAL {score}/3</b>\n"
        f"\n<b>Indicadores</b>\n"
        f"📉 {rsi_label_signal(rsi10, rsi_p)}\n"
        f"📈 {ema_label_signal(epct, q['emaTrend'], q['ema200'])}\n"
        f"📦 {poc_label_signal(ppct, poc)}\n"
        f"🎢 {bb_label_signal(q)}\n"
        f"\n🔍 <b>Análisis</b>\n"
        f"{analisis}\n"
        f"\n<b>Sugerencia</b>\n"
        f"💡 {sugerencia}\n"
        f"\n{_link_tv}"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.3)

    # Acumular en historial del día
    if ticker not in _daily["signals"]:
        _daily["signals"].append(ticker)

# ── 2. Watchlist — Score 2/3 → alerta amarilla individual ────────────────────
for ticker, score, q, epct, ppct in watchlist_found:
    rsi10    = q["rsi10"] or 50
    rsi_p    = q["rsi_prev"] or rsi10
    poc      = q["poc_proxy"] or 0
    fund     = FUND.get(ticker, "buenos")
    div      = q.get("div_bullish", False)
    bb_rec   = q.get("bb_recov", False)
    bb_below = q.get("bb_below", False)
    rsi_bounced_w = (rsi10 > 30 and rsi_p <= 30)

    analisis   = generar_analisis(ticker, score, q, epct, ppct, fund)
    sugerencia = sugerencia_watchlist(score, rsi10, epct, fund, div,
                                      bb_rec, bb_below, rsi_bounced_w)

    _tv_sym_w  = TV_MAP.get(ticker, ticker)
    _link_tv_w = f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym_w}">Ver gráfico en TradingView →</a>'

    if not _header_sent:
        send_telegram(session_header)
        time.sleep(0.3)
        _header_sent = True

    msg = (
        f"🟡 <b>{ticker} — WATCHLIST {score}/3</b>\n"
        f"⚠️ <b>Estado:</b> Setup en formación. Aviso previo — monitorear.\n"
        f"\n<b>Indicadores</b>\n"
        f"📉 {rsi_label_watchlist(rsi10, rsi_p)}\n"
        f"📈 {ema_label_watchlist(epct, q['emaTrend'])}\n"
        f"📦 {poc_label_watchlist(ppct, poc, q['price'])}\n"
        f"🎢 {bb_label_watchlist(q)}\n"
        f"\n🔍 <b>Análisis</b>\n"
        f"{analisis}\n"
        f"\n🛑 <b>Acción sugerida</b>\n"
        f"{sugerencia}\n"
        f"\n{_link_tv_w}"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.5)

    # Acumular en historial del día
    if ticker not in _daily["watchlist"]:
        _daily["watchlist"].append(ticker)

# ── Guardar historial del día ─────────────────────────────────────────────────
try:
    with open("data.json", "r") as f:
        _dj_full = json.load(f)
except Exception:
    _dj_full = {}
_dj_full["daily"] = _daily
with open("data.json", "w") as f:
    json.dump(_dj_full, f)

# ── 3. Reporte Diario — SOLO en CIERRE DE MERCADO ────────────────────────────
if is_cierre:

    # Resumen de alertas del día completo (acumulado)
    _all_sig   = _daily.get("signals", [])
    _all_watch = _daily.get("watchlist", [])

    if not _all_sig and not _all_watch:
        intro = "Hoy no se detectaron señales ni watchlists activas."
    else:
        parts = []
        if _all_sig:
            sig_tickers = ", ".join(f"<b>{t}</b>" for t in _all_sig)
            parts.append(f"<b>{len(_all_sig)}</b> señal(es) confirmada(s) 🟢 ({sig_tickers})")
        if _all_watch:
            wat_tickers = ", ".join(f"<b>{t}</b>" for t in _all_watch)
            parts.append(f"<b>{len(_all_watch)}</b> watchlist(s) 🟡 ({wat_tickers})")
        intro = " · ".join(parts) + "."

    # ── Radar ─────────────────────────────────────────────────────────────────
    def es_radar_valido(q, epct):
        rsi = q.get("rsi10") or 99
        rsi_prev = q.get("rsi_prev") or rsi
        rsi_bounced = rsi > 30 and rsi_prev <= 30
        zona_alerta = 30 <= rsi <= 35
        zona_suelo  = rsi < 30 and not rsi_bounced
        cerca_ema   = abs(epct) <= 1
        return zona_alerta or zona_suelo or cerca_ema

    radar_lines = []
    radar_filtered = [
        (t, q, ep, pp, sc)
        for t, q, ep, pp, sc in radar_info
        if es_radar_valido(q, ep)
    ]
    for ticker, q, epct, ppct, score in sorted(radar_filtered, key=lambda x: x[1]["rsi10"] or 99)[:6]:
        rsi    = q["rsi10"] or 0
        partes = []

        if rsi < 30:
            partes.append(f"RSI(10) en {rsi} — en zona de suelo (oversold)")
        elif rsi <= 35:
            partes.append(f"RSI(10) en {rsi} y bajando hacia 30")

        if abs(epct) <= 1:
            partes.append(f"cerca de testear la EMA200 ({epct:+.1f}%)")
        elif abs(epct) <= 3 and epct < 0:
            partes.append(f"testeando la EMA200 ({epct:.1f}%)")

        if q.get("bb_below"):
            partes.append("Perdió la banda inferior de Bollinger. Sin rebote confirmado")
        elif q.get("bb_near_lo"):
            partes.append("apoyando en banda inferior de BB")

        if score > 0:
            partes.append(f"Score: {score}/3")

        if partes:
            first = partes[0][0].upper() + partes[0][1:]
            rest  = ". ".join(partes[1:])
            line  = f"• <b>{ticker}</b>: {first}"
            line += f". {rest}." if rest else "."
        else:
            line = f"• <b>{ticker}</b>: RSI(10) en {rsi}."

        radar_lines.append(line)

    radar_section = ""
    if radar_lines:
        radar_section = "\n\nActivos bajo observación:\n\n" + "\n".join(radar_lines)

    # Nota dinámica del bot
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

    # El encabezado de cierre va siempre con el reporte (si no se mandó antes)
    if not _header_sent:
        send_telegram(session_header)
        time.sleep(0.3)

    summary_msg = (
        f"📅 <b>Resumen Diario de Mercado — [{date_str}]</b>\n\n"
        f"Resumen: {intro}"
        f"{radar_section}\n\n"
        f"💡 <b>Nota del Bot:</b> {bot_note}"
    )
    print(f"\n{summary_msg}\n")
    send_telegram(summary_msg)

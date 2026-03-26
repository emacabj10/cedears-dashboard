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
    "RSI promedio del universo en zona neutral — esperar definición.",
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
    Genera un análisis contextual de 2-3 líneas según los valores reales del activo.
    Cubre: tendencia/contexto, niveles clave y riesgo del setup.
    """
    rsi10    = q.get("rsi10") or 50
    rsi_prev = q.get("rsi_prev") or rsi10
    ema_trend = q.get("emaTrend") or "lateral"
    div      = q.get("div_bullish", False)
    bb_recov = q.get("bb_recov", False)
    bb_below = q.get("bb_below", False)
    bb_near  = q.get("bb_near_lo", False)
    price    = q.get("price") or 0
    ema200   = q.get("ema200") or 1
    poc      = q.get("poc_proxy") or 1

    lineas = []

    # ── Línea 1: Contexto de tendencia ───────────────────────────────────────
    if epct >= 0 and ema_trend == "subiendo":
        ctx = f"Tendencia alcista de largo plazo intacta (precio {epct:.1f}% sobre EMA200 en ascenso)."
    elif epct >= 0 and ema_trend == "lateral":
        ctx = f"Tendencia lateral — precio sobre EMA200 ({epct:.1f}%) pero sin dirección definida."
    elif epct >= 0 and ema_trend == "bajando":
        ctx = f"EMA200 en descenso ({epct:.1f}% sobre media) — posible agotamiento de tendencia alcista."
    elif epct >= -3:
        ctx = f"Precio testeando la EMA200 ({epct:.1f}%) — zona crítica de soporte dinámico."
    elif epct >= -10:
        ctx = f"Precio por debajo de EMA200 ({epct:.1f}%) en corrección. EMA actúa como resistencia dinámica."
    else:
        ctx = f"Corrección profunda: precio {abs(epct):.1f}% bajo EMA200. Mercado en tendencia bajista de corto plazo."
    lineas.append(ctx)

    # ── Línea 2: Niveles clave y estructura de precio ────────────────────────
    if bb_recov and ppct <= -10:
        niv = f"Rebotó desde la banda inferior de BB con precio {abs(ppct):.1f}% bajo el POC — zona de alto valor histórico."
    elif bb_recov and abs(ppct) <= 5:
        niv = f"Rebote desde BB inferior con precio cerca del POC (${poc:,.0f}) — zona de equilibrio de volumen."
    elif bb_recov:
        niv = f"Recuperó la banda inferior de BB. POC en ${poc:,.0f} ({ppct:+.1f}%) — referencia de valor a monitorear."
    elif bb_below:
        niv = f"Precio fuera de banda inferior — capitulación en curso. POC en ${poc:,.0f} ({ppct:+.1f}%) aún lejos."
    elif bb_near:
        niv = f"Apoyando en banda inferior de BB sin haberla perdido. POC en ${poc:,.0f} ({ppct:+.1f}%)."
    elif ppct <= -15:
        niv = f"Precio {abs(ppct):.1f}% bajo el POC (${poc:,.0f}) — zona de valor profundo, históricamente de acumulación."
    elif ppct <= -5:
        niv = f"Precio acercándose al POC (${poc:,.0f}, {ppct:.1f}%) — potencial zona de rebote por volumen."
    elif abs(ppct) <= 3:
        niv = f"Precio en equilibrio de volumen (POC ${poc:,.0f}) — alta liquidez, zona de decisión."
    else:
        niv = f"Precio {ppct:.1f}% sobre el POC (${poc:,.0f}) — extendido respecto al valor justo."
    lineas.append(niv)

    # ── Línea 3: Riesgo del setup / momentum ─────────────────────────────────
    riesgo_partes = []

    if div:
        riesgo_partes.append("Divergencia alcista RSI confirmada — momentum mejora mientras precio cae")
    elif rsi10 > 30 and rsi_prev <= 30:
        riesgo_partes.append("RSI cruzó al alza el nivel 30 — momentum cambiando a favor")
    elif rsi10 <= 28:
        riesgo_partes.append(f"RSI en oversold extremo ({rsi10}) — zona de máxima presión vendedora")
    elif rsi10 <= 32:
        riesgo_partes.append(f"RSI en {rsi10} saliendo de oversold — confirmar con próxima vela")

    if epct < -10 and score == 3:
        riesgo_partes.append(f"entrada por debajo de EMA200 implica mayor riesgo — ajustá el stop")
    elif epct >= 0 and score == 3:
        riesgo_partes.append("La EMA200 actuando como soporte dinámico valida la estructura alcista de fondo")

    if fund == "excelentes":
        riesgo_partes.append("fundamentals excelentes respaldan el rebote técnico")
    elif fund == "controversiales":
        riesgo_partes.append("fundamentals controversiales — priorizar gestión del riesgo")

    if riesgo_partes:
        # Primera letra en mayúscula, separar con " · "
        riesgo_partes[0] = riesgo_partes[0][0].upper() + riesgo_partes[0][1:]
        lineas.append(" · ".join(riesgo_partes) + ".")

    return "\n".join(lineas)

def sugerencia_signal(score, rsi10, epct, ppct, fund, div, bb_recov):
    """
    Sugerencia contextual para SEÑAL 3/3.
    Solo recomienda entrada cuando score == 3.
    Varía según: zona de valor (ppct), distancia a EMA (epct),
    fundamentals, divergencia y confirmación BB.
    """
    if score != 3:
        return "Señal incompleta. Monitorear — no operar aún."

    # Caso 1: zona de valor profunda + fundamentals sólidos
    if ppct <= -15 and fund in ("excelentes", "buenos"):
        return (
            "Setup completo en zona de valor profunda. "
            "Entrada con posición completa — el precio está históricamente barato. "
            "Fase de acumulación institucional detectada. "
        )

    # Caso 2: divergencia alcista activa (señal de mayor calidad)
    if div:
        return (
            "Setup con divergencia alcista confirmada — mayor calidad de señal. "
            "Entrada válida con posición completa. "
            "Ampliá si la siguiente vela confirma continuidad alcista."
        )

    # Caso 3: corrección profunda (precio muy por debajo de EMA200)
    if epct < -10:
        return (
            f"Rebote técnico con precio {abs(epct):.1f}% bajo EMA200 — tendencia bajista de fondo vigente. "
            "Entrada con media posición. "
            "Precio con descuento respecto a la media.."
        )

    # Caso 4: testeando EMA200 como soporte dinámico
    if -3 <= epct < 0:
        return (
            "Setup sobre soporte dinámico (EMA200). "
            "Entrada con media posición — confirmá que el precio no pierde la media en la próxima vela. "
            "Mantener ritmo de acumulación."
        )

    # Caso 5: precio extendido sobre POC (riesgo de toma de ganancias)
    if ppct >= 20:
        return (
            f"Setup válido pero precio {ppct:.1f}% sobre el POC — extendido respecto al valor justo. "
            "Entrada con media posición. "
            "Precio extendido, POC como referencia.".format(ppct)
        )

    # Caso 6: fundamentals controversiales
    if fund == "controversiales":
        return (
            "Setup técnico confirmado en activo con fundamentals controversiales. "
            "Entrada con media posición. "
            "No extendas el horizonte temporal más allá del setup."
        )

    # Caso estándar: señal limpia sobre EMA con BB recuperado
    if epct >= 0 and bb_recov:
        return (
            "Setup limpio: RSI rebotó, precio sobre EMA200 y recuperó banda BB. "
            "Entrada con media posición. Chequeá divergencias en TradingView para ampliar convicción."
        )

    # Default
    return (
        "Setup válido. Entrada confirmada con media posición según tu plan de riesgo. "
        "Verificá niveles en TradingView antes de ejecutar."
    )


def sugerencia_watchlist(score, rsi10, epct, ppct, fund, div, bb_recov, bb_below, rsi_bounced):
    """
    Sugerencia contextual para WATCHLIST 2/3.
    Siempre indica NO OPERAR, pero describe exactamente qué condición falta
    y qué vigilar según los 2 puntos que ya se cumplieron.
    """
    ema_ok   = epct >= -3
    rsi_ok   = rsi_bounced
    bb_ok    = bb_recov

    # Caso 1: tiene EMA + BB, falta RSI (más común en watchlist)
    if ema_ok and bb_ok and not rsi_ok:
        if rsi10 <= 30:
            return (
                "NO OPERAR aún. Falta confirmar el cruce del RSI sobre 30. "
                f"RSI actual en {rsi10} — oversold pero sin rebote confirmado. "
                "Activá alerta en TradingView para RSI(10) cruzando 30 al alza."
            )
        else:
            return (
                "NO OPERAR aún. EMA200 y BB recuperados, pero RSI no cruzó el nivel 30 en la vela anterior. "
                f"RSI actual en {rsi10} — esperá que baje a zona de oversold y rebote. "
                "Setup en formación, puede madurar en próximas ruedas."
            )

    # Caso 2: tiene RSI + EMA, falta BB (precio no recuperó la banda)
    if rsi_ok and ema_ok and not bb_ok:
        if bb_below:
            return (
                "NO OPERAR. RSI rebotó y precio sobre EMA200, pero sigue fuera de la banda inferior de BB. "
                "Esperá que el precio cierre dentro de las bandas para confirmar el rebote. "
                "La recuperación de la banda BB es la confirmación que falta."
            )
        else:
            return (
                "NO OPERAR. RSI rebotó y precio sobre EMA200, pero aún no se dio el rebote desde la banda BB. "
                f"Precio cerca de la banda inferior — monitorear. "
                "Si BB se recupera en próxima vela, setup completo."
            )

    # Caso 3: tiene RSI + BB, falta EMA (precio bajo EMA200)
    if rsi_ok and bb_ok and not ema_ok:
        return (
            f"NO OPERAR. RSI y BB confirmados, pero precio {abs(epct):.1f}% bajo EMA200 — resistencia dinámica activa. "
            "El setup es válido técnicamente pero opera en contra de la tendencia de largo plazo. "
            "Reducí el tamaño de posición si decidís entrar cuando se complete la señal."
        )

    # Caso 4: divergencia activa → monitoreo prioritario
    if div:
        return (
            "NO OPERAR aún, pero divergencia alcista activa — setup de alta prioridad. "
            "El momentum está mejorando mientras el precio cae. "
            f"Falta {'RSI' if not rsi_ok else 'BB' if not bb_ok else 'EMA'} para completar la señal. Monitorear de cerca."
        )

    # Caso 5: precio cerca del POC
    if abs(ppct) <= 5:
        return (
            f"NO OPERAR. Setup en formación sobre el POC (${ppct:.0f}% del valor justo) — zona de decisión. "
            "Esperá validación de soporte en este nivel antes de entrar. "
            "Un cierre firme sobre el POC con RSI en recuperación sería la confirmación ideal."
        )

    # Default watchlist
    return (
        "NO OPERAR. Setup en formación — falta al menos una confirmación técnica. "
        "Esperá el cruce del RSI al alza sobre 30 o validación de soporte en el POC."
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

    poc_max_op = fund_ex and ppct <= -25 and ppct >= -40

    # Setup en formación: RSI ≤ 38 sin rebote confirmado
    forming_rsi_zone = (rsi10 <= 38 and not rsi_bounced)
    forming = forming_rsi_zone

    return score, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold

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
print(f"CEDEARS ALERTAS — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
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
        _, _, epct, ppct, _, _, _, _ = score_signal(ticker, q)
        all_results.append((ticker, 0, q, epct, ppct))
        if rsi10 <= 38:
            radar_info.append((ticker, q, epct, ppct, 0))
        continue

    score, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold = \
        score_signal(ticker, q)
    all_results.append((ticker, score, q, epct, ppct))

    rsi10 = q["rsi10"] or 50

    if score == 3 and rsi_bounced:
        print(f"  >>> SEÑAL 3/3: {ticker} rsi={rsi10} rsi_prev={q.get('rsi_prev')} bb_recov={q.get('bb_recov')} epct={epct:.1f}")
        signals_found.append((ticker, score, q, epct, ppct, fund, poc_max_op))
    elif score == 2 and not rsi_bounced and rsi10 <= 38:
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → watchlist")
        watchlist_found.append((ticker, score, q, epct, ppct))
    elif (rsi10 <= 35) or (rsi10 < 30 and not rsi_bounced) or (abs(epct) <= 1):
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → radar")
        radar_info.append((ticker, q, epct, ppct, score))
    else:
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → ignorado")

    time.sleep(0.5)

# Watchlists ordenadas por RSI ascendente
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

# ── 1. Señales confirmadas (Score 3/3) → alerta verde individual ──────────────
for ticker, score, q, epct, ppct, fund, poc_max_op in signals_found:
    rsi10  = q["rsi10"] or 50
    rsi_p  = q["rsi_prev"] or rsi10
    poc    = q["poc_proxy"] or 0
    div    = q.get("div_bullish", False)
    bb_rec = q.get("bb_recov", False)

    poc_badge = ""
    if poc_max_op:
        poc_badge = f"\n⭐ <b>Máxima oportunidad</b> — {ppct:.1f}% bajo POC · Fundamentals excelentes\n"

    sugerencia = sugerencia_signal(score, rsi10, epct, ppct, fund, div, bb_rec)
    analisis   = generar_analisis(ticker, score, q, epct, ppct, fund)

    msg = (
        f"🟢 <b>{ticker} — SEÑAL {score}/3</b>\n"
        f"{poc_badge}"
        f"\n<b>Indicadores</b>\n"
        f"📉 {rsi_label_signal(rsi10, rsi_p)}\n"
        f"📈 {ema_label_signal(epct, q['emaTrend'], q['ema200'])}\n"
        f"📦 {poc_label_signal(ppct, poc)}\n"
        f"🎢 {bb_label_signal(q)}\n"
        f"\n🔍 <b>Análisis</b>\n"
        f"{analisis}\n"
        f"\n<b>Sugerencia</b>\n"
        f"💡 {sugerencia}"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.3)

# ── 2. Watchlist — Score 2/3 → alerta amarilla individual ────────────────────
for ticker, score, q, epct, ppct in watchlist_found:
    rsi10    = q["rsi10"] or 50
    rsi_p    = q["rsi_prev"] or rsi10
    poc      = q["poc_proxy"] or 0
    fund     = FUND.get(ticker, "buenos")
    div      = q.get("div_bullish", False)
    bb_rec   = q.get("bb_recov", False)
    bb_below = q.get("bb_below", False)
    # Para watchlist: rsi_bounced es False por definición (condición de entrada)
    rsi_bounced_w = (rsi10 > 30 and rsi_p <= 30)

    analisis   = generar_analisis(ticker, score, q, epct, ppct, fund)
    sugerencia = sugerencia_watchlist(score, rsi10, epct, ppct, fund, div,
                                      bb_rec, bb_below, rsi_bounced_w)

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
        f"{sugerencia}"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.5)

# ── 3. Resumen Diario / Radar ─────────────────────────────────────────────────
total_sig   = len(signals_found)
total_watch = len(watchlist_found)

if total_sig == 0 and total_watch == 0:
    intro = "Hoy no se detectaron señales ni watchlists activas."
else:
    parts = []
    if total_sig:
        sig_tickers = ", ".join(f"<b>{t}</b>" for t, *_ in signals_found)
        parts.append(f"<b>{total_sig}</b> señal(es) confirmada(s) 🟢 ({sig_tickers})")
    if total_watch:
        parts.append(f"<b>{total_watch}</b> watchlist(s) enviada(s) 🟡")
    intro = " · ".join(parts) + "."

# ── Radar: solo activos CERCA de dar señal ────────────────────────────────────
# Filtros:
#   Zona de Alerta : RSI entre 30 y 35 (aproximándose al suelo)
#   Zona de Suelo  : RSI < 30 sin rebote confirmado
#   Cerca de EMA   : precio a menos del 1% de la EMA200 (aunque RSI sea neutral)
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
    rsi = q["rsi10"] or 0
    line = f"• <b>{ticker}</b>: RSI(10) en {rsi}"

    if rsi < 30:
        # Zona de Suelo: RSI ya está en oversold, sin rebote confirmado
        line += ". En zona de suelo (oversold)."
        if q.get("bb_below"):
            line += " Perdió la banda inferior de Bollinger. Sin rebote confirmado."
        if score > 0:
            line += f" Score actual: {score}/3."
    elif rsi <= 35:
        # Zona de Alerta: aproximándose al suelo
        line += " y bajando hacia 30."
        if q.get("bb_below"):
            line += " Perdió la banda inferior de Bollinger. Sin rebote confirmado."
        if score > 0:
            line += f" Score actual: {score}/3."
    elif abs(epct) <= 1:
        line += f". Cerca de testear la EMA200."
        if score > 0:
            line += f" Score actual: {score}/3."
    else:
        if score > 0:
            line += f". Score actual: {score}/3."

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

summary_msg = (
    f"📅 <b>Resumen Diario de Mercado — [{date_str}]</b>\n\n"
    f"Resumen: {intro}"
    f"{radar_section}\n\n"
    f"💡 <b>Nota del Bot:</b> {bot_note}"
)
print(f"\n{summary_msg}\n")
send_telegram(summary_msg)

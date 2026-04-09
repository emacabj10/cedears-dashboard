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
    "ETH":"buenos","BNB":"buenos","GLD":"buenos",
    "AMD":"buenos","KO":"buenos","PEP":"buenos",
    "MCD":"buenos","BABA":"buenos","TSLA":"controversiales",


}

# Mapa TradingView: símbolo exacto para la URL del gráfico
TV_MAP = {
    "MSFT":"NASDAQ:MSFT","GOOGL":"NASDAQ:GOOGL","AMZN":"NASDAQ:AMZN",
    "META":"NASDAQ:META","BRK.B":"NYSE:BRK.B","V":"NYSE:V",
    "WMT":"NYSE:WMT","MELI":"NASDAQ:MELI","QQQ":"NASDAQ:QQQ",
    "SPY":"AMEX:SPY","DIA":"AMEX:DIA","AMD":"NASDAQ:AMD",
    "KO":"NYSE:KO","PEP":"NASDAQ:PEP","MCD":"NYSE:MCD",
    "BABA":"NYSE:BABA","TSLA":"NASDAQ:TSLA",
    "GLD":"AMEX:GLD","BTC":"BINANCE:BTCUSDT","ETH":"BINANCE:ETHUSDT",
    "BNB":"BINANCE:BNBUSDT",


}

YF_MAP = {
    "AMD":"AMD","AMZN":"AMZN","BABA":"BABA","BNB":"BNB-USD",
    "BRK.B":"BRK-B","BTC":"BTC-USD","DIA":"DIA","ETH":"ETH-USD",
    "GOOGL":"GOOGL","KO":"KO","MCD":"MCD","MELI":"MELI","META":"META",
    "MSFT":"MSFT","PEP":"PEP","QQQ":"QQQ",
    "SPY":"SPY","TSLA":"TSLA","V":"V","WMT":"WMT","GLD":"GLD",


}

BOT_NOTES = [
    "Día de paciencia. El mercado está en fase de consolidación.",
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
    if len(closes) < period+20: return "lateral"
    k = 2/(period+1)
    ema = sum(closes[:period])/period
    emas = []
    for c in closes[period:]:
        ema = c*k + ema*(1-k); emas.append(ema)
    last20 = emas[-20:]
    slope = (last20[-1]-last20[0])/last20[0]*100
    return "subiendo" if slope>1.5 else ("bajando" if slope<-1.5 else "lateral")

def calc_ema_slope(closes, period=200):
    """Slope numérico de la EMA200 sobre los últimos 20 días (% de cambio).
    Positivo = EMA subiendo. Umbral > 0.8% confirma tendencia alcista sostenida."""
    if len(closes) < period + 20: return 0.0
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    emas = []
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
        emas.append(ema)
    last20 = emas[-20:]
    return round((last20[-1] - last20[0]) / last20[0] * 100, 3)

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
        ema_slope = calc_ema_slope(closes, 200)
        bb_lo     = calc_bb_lower(closes, 20, 2)
        bb_lo_prev = calc_bb_lower(closes[:-1], 20, 2)
        bb_hi     = calc_bb_upper(closes, 20, 2)
        bb_wid    = calc_bb_width(closes, 20, 2)
        poc_proxy = calc_poc_proxy(closes)
        price_prev = closes[-2] if len(closes) >= 2 else price

        # ── Rebote Bollinger — ventana de 5 velas ────────────────────────────
        # Alguna de las últimas 4 velas cerró debajo de bb_lo en ese momento,
        # y la vela actual cerró encima (recuperó la banda).
        # price > price_prev confirma momentum alcista — filtra dead cat bounces.
        bb_recov = False
        if bb_lo is not None and price >= bb_lo and price > price_prev:
            for lookback in range(1, 6):   # velas 1..5 hacia atrás
                if len(closes) > lookback:
                    past_close = closes[-(lookback + 1)]
                    past_bb_lo = calc_bb_lower(closes[:-(lookback)], 20, 2)
                    if past_bb_lo is not None and past_close < past_bb_lo:
                        bb_recov = True
                        break

        bb_below   = price < bb_lo if bb_lo else False
        bb_above   = price > bb_hi if bb_hi else False
        bb_squeeze = (bb_wid[0] < bb_wid[1] * 0.85) if bb_wid else False
        bb_near_lo = (not bb_below) and bb_lo and ((price - bb_lo) / bb_lo * 100 < 2)

        # ── Historial RSI — ultimas 15 velas ───────────────────────────────────
        rsi_history = []
        for lookback in range(15, 0, -1):   # vela 15 atras -> vela 1 atras
            if len(closes) > lookback:
                past_rsi = calc_rsi(closes[:-(lookback)], 10)
                if past_rsi is not None:
                    rsi_history.append(round(past_rsi, 2))

        # rsi_bounced_15: el RSI tocó <=30 en las últimas 15 velas Y está
        # subiendo desde ese mínimo — es decir, el RSI actual es mayor que
        # el mínimo registrado Y mayor que el RSI de la vela anterior.
        # Esto evita falsos positivos cuando el RSI bajó a 28 hace 12 velas
        # pero ahora está en 42 bajando de nuevo.
        _rsi_min_in_window = min(rsi_history) if rsi_history else 100
        rsi_bounced_15 = (
            rsi10 is not None
            and rsi_prev is not None
            and rsi10 > 30                        # salió del oversold
            and _rsi_min_in_window <= 30           # sí tocó <=30 en la ventana
            and rsi10 > rsi_prev                   # RSI subiendo (momentum alcista)
        )

        # ── Divergencia alcista — ventana de 15 velas ────────────────────────
        # Mínimo de precio reciente más bajo que mínimo anterior,
        # pero RSI en ese punto más alto que RSI en el mínimo anterior.
        div_bullish = False
        if rsi10 is not None and len(closes) >= 30:
            window = 15
            # Ventana reciente: últimas 15 velas (sin la actual)
            rec_closes = closes[-(window + 1):-1]
            # Ventana anterior: las 15 velas previas a esa
            ant_closes = closes[-(window * 2 + 1):-(window + 1)]

            if len(rec_closes) == window and len(ant_closes) == window:
                # Índice del mínimo en cada ventana
                idx_rec = rec_closes.index(min(rec_closes))
                idx_ant = ant_closes.index(min(ant_closes))

                min_price_rec = rec_closes[idx_rec]
                min_price_ant = ant_closes[idx_ant]

                # RSI calculado hasta ese punto en cada ventana
                rsi_at_rec = calc_rsi(closes[:-(window + 1) + idx_rec + 1], 10)
                rsi_at_ant = calc_rsi(closes[:-(window * 2 + 1) + idx_ant + 1], 10)

                if (rsi_at_rec is not None and rsi_at_ant is not None
                        and min_price_rec < min_price_ant   # precio: mínimo más bajo
                        and (min_price_ant - min_price_rec) / min_price_ant >= 0.02  # separación mínima 2%
                        and rsi_at_rec > rsi_at_ant):       # RSI: mínimo más alto
                    div_bullish = True

        return {
            "price":price,"rsi10":rsi10,"rsi_prev":rsi_prev,
            "rsiW":rsi_w,"ema200":ema200,"emaTrend":ema_trend,"emaSlope":ema_slope,
            "bb_lo":bb_lo,"bb_hi":bb_hi,"bb_recov":bb_recov,
            "bb_below":bb_below,"bb_above":bb_above,
            "bb_squeeze":bb_squeeze,"bb_near_lo":bb_near_lo,
            "poc_proxy":poc_proxy,
            "div_bullish": div_bullish,
            "price_prev": price_prev,
            "bb_lo_prev": bb_lo_prev,
            "rsi_bounced_15": rsi_bounced_15,
            "rsiHistory": rsi_history,
        }
    except Exception as e:
        print(f"  Error: {e}"); return None

def fetch_price_only(sym):
    """Fetch liviano: solo precio actual vía Yahoo Finance (sin historial completo).
    Usado en el chequeo intradiario para confirmar que la señal del cierre anterior
    sigue activa — no recalcula RSI ni indicadores.
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
    headers = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        return round(closes[-1], 2) if closes else None
    except Exception as e:
        print(f"  [price_only] Error {sym}: {e}"); return None

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
        return f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Zona de valor estimada (Desviación importante respecto al precio histórico)"
    elif ppct <= -15:
        return f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Zona de valor estimada (Precio históricamente barato)"
    elif ppct <= -5:
        return f"POC: {ppct:.1f}% bajo (${poc:,.0f}) — Cerca de zona de valor estimada"
    elif abs(ppct) <= 2:
        return f"POC: ${poc:,.0f} — En zona de equilibrio estimada (aprox.)"
    else:
        return f"POC: +{ppct:.1f}% sobre (${poc:,.0f}) — Extendido sobre valor estimado (Posible toma de ganancias)"

def poc_label_watchlist(ppct, poc, price):
    """Labels POC para watchlist"""
    if ppct <= -10:
        return f"POC: -{abs(ppct):.1f}% — Por debajo de zona de valor estimada (Posible oportunidad en desarrollo)"
    elif ppct <= -2:
        return f"POC: ${poc:,.0f} — Precio actual ${price:,} (Aproximándose a zona de equilibrio estimada)"
    elif abs(ppct) <= 2:
        return f"POC: ${poc:,.0f} — En zona de equilibrio estimada (aprox.)"
    else:
        return f"POC: +{ppct:.1f}% sobre (${poc:,.0f}) — Sobre valor estimado"

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
    Contexto compacto sin redundar lo que ya muestran los indicadores.
    Línea 1 — Contexto de mercado (tendencia, fase)
    Línea 2 — Dato diferencial: divergencia, impulso RSI o estado de capitulación
    """
    rsi10     = q.get("rsi10") or 50
    rsi_prev  = q.get("rsi_prev") or rsi10
    ema_trend = q.get("emaTrend") or "lateral"
    div       = q.get("div_bullish", False)
    bb_recov  = q.get("bb_recov", False)
    bb_below  = q.get("bb_below", False)
    bb_near   = q.get("bb_near_lo", False)

    lineas = []

    # ── Línea 1: Contexto de mercado (sin repetir el label de EMA) ───────────
    if epct >= 0 and ema_trend == "subiendo":
        ctx = "Tendencia alcista de largo plazo intacta. Corrección técnica dentro de estructura positiva."
    elif epct >= 0 and ema_trend == "lateral":
        ctx = "Mercado lateralizando sobre la EMA200 sin tendencia definida."
    elif epct >= 0 and ema_trend == "bajando":
        ctx = "EMA200 perdiendo pendiente — señal de agotamiento de tendencia alcista. Corrección en desarrollo."
    elif epct >= -5:
        ctx = "Precio en zona de decisión crítica sobre la EMA200. Un cierre por encima confirma el soporte dinámico."
    elif epct >= -10:
        ctx = f"Corrección moderada bajo EMA200. La media actúa como resistencia dinámica en el corto plazo."
    else:
        ctx = f"Corrección profunda ({abs(epct):.1f}% bajo EMA200). Zona de capitulación con tendencia bajista de corto plazo vigente."
    lineas.append(ctx)

    # ── Línea 2: Dato diferencial (impulso, divergencia, capitulación) ───────
    if div:
        lineas.append(f"Divergencia alcista confirmada — precio hace mínimo más bajo pero el RSI marca mínimo más alto. Cambio de impulso favorable.")
    elif rsi10 > 30 and rsi_prev <= 30:
        lineas.append(f"RSI cruzó al alza el nivel 30 desde {rsi_prev} — impulso girando a favor del comprador.")
    elif bb_recov and bb_below:
        lineas.append("Recuperó la banda inferior de BB luego de haberla perdido — capitulación resuelta.")
    elif rsi10 <= 28:
        lineas.append(f"RSI en oversold extremo ({rsi10}) — presión vendedora en máximos, históricamente precede rebotes.")
    elif rsi10 <= 32 and rsi10 > rsi_prev:
        lineas.append(f"RSI en {rsi10} con pendiente alcista desde {rsi_prev} — impulso recuperándose desde zona de suelo.")
    elif bb_near:
        lineas.append("Apoyando en banda inferior de BB — zona de posible capitulación y rebote técnico.")

    return "\n".join(lineas)


def sugerencia_signal(score, rsi10, epct, fund, div, bb_recov, ema_ok=None, ema_ok_media=None):
    """
    Solo decisión operativa — sin repetir datos técnicos que ya están en Contexto.
    score 3         = señal completa
    score 2 + div   = señal promovida por divergencia
    ema_ok          = precio dentro del -5% de EMA  → posición completa
    ema_ok_media    = precio entre -5% y -10% de EMA → posición media
    """
    if score not in (2, 3):
        return "Señal incompleta. Monitorear — no operar aún."

    # Calcular flags si no vienen del caller
    if ema_ok is None:       ema_ok       = epct >= -5
    if ema_ok_media is None: ema_ok_media = epct >= -10

    # Señal promovida por divergencia (score 2): más conservador
    if score == 2 and div:
        if ema_ok:
            return (
                "Entrada con media posición. "
                "Ampliá a posición completa cuando el setup complete los 3 puntos."
            )
        else:
            return (
                f"Entrada con media posición ({abs(epct):.1f}% bajo EMA200). "
                "Esperá confirmación adicional antes de ampliar."
            )

    # Con divergencia en señal 3/3 + cerca EMA: entrada reforzada
    if div and ema_ok:
        return (
            "Entrada con posición completa. "
            "Ampliá si la siguiente vela confirma continuidad alcista."
        )

    # Precio sobre EMA200 + BB: setup más limpio posible
    if epct >= 0 and bb_recov:
        return (
            "Entrada con posición completa. "
            "La EMA200 actúa como soporte dinámico de largo plazo."
        )

    # Testeando EMA200 (dentro del -5%) + BB recuperado
    if ema_ok and bb_recov:
        return (
            "Entrada con posición completa. "
            "Zona de confluencia técnica — favorable para acumulación."
        )

    # Entre -5% y -10% de EMA: posición media, esperar recuperación
    if ema_ok_media and not ema_ok:
        return (
            f"Entrada con media posición ({abs(epct):.1f}% bajo EMA200). "
            "Ampliá a posición completa cuando el precio recupere la media."
        )

    # Default conservador
    return (
        "Entrada con media posición. "
        "Confirmá tendencia en TradingView antes de ejecutar."
    )


def sugerencia_watchlist(score, rsi10, epct, fund, div, bb_recov, bb_below, rsi_bounced):
    """
    Solo indica qué falta y qué hacer — sin repetir datos técnicos ya visibles en Contexto.
    """
    ema_ok = epct >= -5
    rsi_ok = rsi_bounced
    bb_ok  = bb_recov

    # Caso 1: EMA + BB confirmados, falta RSI
    if ema_ok and bb_ok and not rsi_ok:
        if rsi10 <= 30:
            return "Esperá el cruce del RSI sobre 30. Cuando cruce, los 3 puntos estarán completos: entrada con posición completa."
        else:
            return f"Falta que el RSI baje a oversold y rebote sobre 30. El setup puede madurar en las próximas ruedas."

    # Caso 2: RSI + EMA confirmados, falta BB
    if rsi_ok and ema_ok and not bb_ok:
        if bb_below:
            return "Esperá que el precio cierre dentro de las bandas de BB — es la confirmación que falta."
        else:
            return "Falta el rebote desde la banda inferior de BB. Monitorear: si presiona y rebota, setup completo."

    # Caso 3: RSI + BB confirmados, falta EMA
    if rsi_ok and bb_ok and not ema_ok:
        return (
            f"Falta recuperar la EMA200 (precio {abs(epct):.1f}% abajo). "
            "Cuando complete, entrada con media posición — ampliá si el precio recupera la media."
        )

    # Caso 4: divergencia activa
    if div:
        falta = "RSI" if not rsi_ok else ("BB" if not bb_ok else "EMA")
        return (
            f"Falta confirmar {falta} para completar la señal. "
            "Cuando se complete, entrada con posición completa."
        )

    # Caso 5: RSI cerca de oversold
    if rsi10 <= 35:
        return "Esperá las confirmaciones faltantes. Si completa los 3 puntos desde esta zona, entrada de alta calidad."

    # Default
    return "Esperá que los 3 puntos se confirmen antes de entrar. No anticipar el setup."

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

    # ── Punto 1: RSI cruzando al alza el nivel de 30 — ventana 15 velas ────────
    rsi_bounced    = (rsi10 > 30 and rsi_prev <= 30)           # 1 vela (fallback)
    rsi_bounced_15 = q.get("rsi_bounced_15", rsi_bounced)      # 15 velas (preciso)
    rsi_oversold   = rsi10 <= 30

    if rsi_bounced_15:
        score += 1

    # ── Punto 2: EMA200 — dos niveles ──────────────────────────────────────────
    # ema_ok       : precio dentro del -5%  → posición completa
    # ema_ok_media : precio entre -5% y -10% → posición media
    # Ambos suman el punto; la sugerencia de tamaño la maneja sugerencia_signal
    ema_ok       = epct >= -5
    ema_ok_media = epct >= -10
    if ema_ok or ema_ok_media:
        score += 1

    # ── Punto 3: Bollinger — recuperó banda inferior ──────────────────────────
    if q.get("bb_recov"):
        score += 1

    # Setup en formación: RSI ≤ 38 sin rebote confirmado
    forming_rsi_zone = (rsi10 <= 38 and not rsi_bounced_15)
    forming = forming_rsi_zone

    return score, forming, epct, ppct, fund, rsi_bounced_15, rsi_oversold, ema_ok, ema_ok_media

def squeeze_note(q):
    """Devuelve una línea de advertencia si hay BB squeeze, vacío si no."""
    if q.get("bb_squeeze"):
        return "\n⚠️ <b>Nota:</b> BB en compresión — esperar ruptura de rango antes de ejecutar."
    return ""

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
            return
    except Exception as e:
        print(f"  Telegram HTML error: {e}")
        print(f"  MSG DUMP: {repr(message[:300])}")
    import re
    plain = re.sub(r"<[^>]+>", "", message)
    payload2 = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": plain}).encode()
    req2 = urllib.request.Request(url, data=payload2,
                                  headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req2, timeout=10) as r:
            print(f"  Telegram OK plain ({r.status})")
    except Exception as e:
        print(f"  Telegram plain error: {e}")

def send_telegram_with_button(message, ticker):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Sin credenciales:\n" + message); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    keyboard = {"inline_keyboard": [[{"text": "✅ Operada", "callback_data": f"operado:{ticker}"}]]}
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID, "text": message,
        "parse_mode": "HTML", "reply_markup": keyboard
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  Telegram+button OK ({r.status})")
            return
    except Exception as e:
        print(f"  Telegram button error: {e}")
        send_telegram(message)

def answer_callback_query(callback_query_id, text="✅ Registrado"):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = json.dumps({
        "callback_query_id": callback_query_id,
        "text": text, "show_alert": False
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  answerCallback OK ({r.status})")
    except Exception as e:
        print(f"  answerCallback error: {e}")

def handle_operado(ticker_cmd):
    """
    Llamado cuando el usuario responde !operado TICKER desde Telegram.
    Silencia el ticker y registra la entrada en data.json.
    """
    ticker_cmd = ticker_cmd.strip().upper()
    if ticker_cmd not in YF_MAP:
        print(f"  [OPERADO] {ticker_cmd} no reconocido")
        return

    try:
        with open("data.json", "r") as f:
            dj = json.load(f)
    except Exception:
        dj = {}

    # Activar silencio
    # Detectar posicion automaticamente segun epct al momento de operar
    cycs = dj.get("cycles", {})
    quotes_data = dj.get("quotes", {})
    posicion = "completa"  # default
    if ticker_cmd in quotes_data:
        _price  = quotes_data[ticker_cmd].get("price", 0)
        _ema200 = quotes_data[ticker_cmd].get("ema200", 0) or 1
        _epct   = (_price - _ema200) / _ema200 * 100
        posicion = "completa" if _epct >= -5 else "media"
    cycs[ticker_cmd] = {
        "is_silenced": True,
        "rsi_hit_50":  False,
        "rsi_reset":   False,
        "posicion":    posicion,
    }
    dj["cycles"] = cycs
    print(f"  [OPERADO] posicion detectada: {posicion} (epct guardado en ciclo)")

    # Registrar entrada del día
    today = now_arg().strftime("%Y-%m-%d")
    daily = dj.get("daily", {"date": today, "signals": [], "watchlist": [], "entradas": []})
    if "entradas" not in daily:
        daily["entradas"] = []

    # Buscar precio del ticker en quotes si está disponible
    price_str = ""
    quotes = dj.get("quotes", {})
    if ticker_cmd in quotes:
        price_str = f"${quotes[ticker_cmd].get('price', 0):,.2f}"

    hora_str = now_arg().strftime("%H:%M")
    entrada = {"ticker": ticker_cmd, "price": price_str, "hora": hora_str}
    if not any(e["ticker"] == ticker_cmd for e in daily["entradas"]):
        daily["entradas"].append(entrada)
    dj["daily"] = daily

    with open("data.json", "w") as f:
        json.dump(dj, f, indent=2, ensure_ascii=False)

    print(f"  [OPERADO] {ticker_cmd} silenciado. Ciclo iniciado.")
    pos_emoji = "💯" if posicion == "completa" else "⚡"
    pos_label = "posición completa" if posicion == "completa" else "media posición"
    send_telegram(
        f"✅ <b>{ticker_cmd}</b> marcado como operado.\n"
        f"Entrada registrada como <b>{pos_label}</b>.\n"
        f"El bot silenciará alertas de Señal/Watchlist hasta completar el ciclo.\n"
    )

# Procesar comando operado — soporta dos fuentes:
# 1. Botón inline: CMD_OPERADO=operado:GLD  (callback_data del botón)
# 2. Texto manual: CMD_OPERADO=!operado GLD (fallback por texto)
_cmd_operado = os.environ.get("CMD_OPERADO", "").strip()
_cbq_id      = os.environ.get("CALLBACK_QUERY_ID", "").strip()  # para answerCallbackQuery

if _cmd_operado.lower().startswith("operado:"):
    # Formato botón inline: operado:GLD
    _ticker_op = _cmd_operado.split(":", 1)[1]
    handle_operado(_ticker_op)
    if _cbq_id:
        answer_callback_query(_cbq_id, "✅ Entrada registrada")
    import sys; sys.exit(0)
elif _cmd_operado.lower().startswith("!operado "):
    # Formato texto manual: !operado GLD
    _ticker_op = _cmd_operado.split(" ", 1)[1]
    handle_operado(_ticker_op)
    import sys; sys.exit(0)
# ── Main ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"CEDEARS ALERTAS — {now_arg().strftime('%d/%m/%Y %H:%M')} (ARG)")
print(f"{'='*55}\n")

signals_found   = []   # score 3/3  → alerta verde individual
watchlist_found = []   # score 2/3  → alerta amarilla individual
radar_info      = []   # score 0-1  → solo en reporte de cierre
all_results     = []

existing = {}
cycles   = {}   # ciclos de acumulación por ticker
try:
    with open("data.json","r") as f:
        dj = json.load(f)
        existing = dj.get("quotes", {})
        cycles   = dj.get("cycles", {})
except: pass

def get_cycle(ticker):
    """Devuelve el estado del ciclo para un ticker.
    Estructura: {is_silenced, rsi_hit_50, rsi_reset}
    """
    return cycles.get(ticker, {
        "is_silenced": False,
        "rsi_hit_50":  False,
        "rsi_reset":   False,
    })

def save_cycle(ticker, state):
    cycles[ticker] = state

# ── Modo Intradiario ─────────────────────────────────────────────────────────
# INTRADAY_CHECK=1 → chequeo liviano: solo precio actual vs EMA200 y RSI del
# cierre anterior guardado en data.json. No recalcula indicadores. No genera
# reportes de cierre. Solo dispara si la señal sigue activa Y no fue enviada hoy.
_INTRADAY = os.environ.get("INTRADAY_CHECK", "0").strip() == "1"

if _INTRADAY:
    print("\n[INTRADAY] Modo chequeo intradiario liviano activado.")
    _today_intra = now_arg().strftime("%Y-%m-%d")
    try:
        with open("data.json", "r") as f:
            _dj_intra = json.load(f)
    except Exception:
        print("[INTRADAY] Sin data.json — abortando."); import sys; sys.exit(0)

    _quotes_saved  = _dj_intra.get("quotes", {})
    _daily_intra   = _dj_intra.get("daily", {})
    _cycles_intra  = _dj_intra.get("cycles", {})

    # Resetear daily si cambió la fecha
    if _daily_intra.get("date") != _today_intra:
        _daily_intra = {"date": _today_intra, "signals": [], "watchlist": [], "entradas": []}

    _intra_header_sent = False
    _intra_fired = []

    # Sesión según hora Argentina — igual que el bot normal
    _intra_hour = now_arg().hour
    if 9 <= _intra_hour < 13:
        _intra_session = "APERTURA DE MERCADO"
    elif 13 <= _intra_hour < 16:
        _intra_session = "MEDIA RUEDA DE MERCADO"
    else:
        _intra_session = "CIERRE DE MERCADO"

    for ticker, sym in YF_MAP.items():
        saved = _quotes_saved.get(ticker)
        if not saved:
            print(f"  [INTRADAY] {ticker}: sin datos guardados — skip")
            continue

        # Skip si ya fue alertado hoy — con lógica de upgrade
        _intra_in_signals   = ticker in set(_daily_intra.get("signals", []))
        _intra_in_watchlist = ticker in set(_daily_intra.get("watchlist", []))

        # Para evaluar upgrade necesitamos los datos guardados primero
        # (los leemos abajo; acá solo skip definitivo si ya está en señal)
        if _intra_in_signals:
            print(f"  [INTRADAY] {ticker}: señal ya enviada hoy — skip")
            continue

        # Skip si está silenciado (ciclo activo)
        cyc_intra = _cycles_intra.get(ticker, {})
        if cyc_intra.get("is_silenced"):
            print(f"  [INTRADAY] {ticker}: silenciado (ciclo) — skip")
            continue

        # Leer datos del cierre anterior desde data.json
        rsi_prev_close  = saved.get("rsi10")       # RSI del último cierre diario
        ema200_saved    = saved.get("ema200")
        rsi_bounced_15  = saved.get("rsi_bounced_15", False)
        bb_recov_saved  = saved.get("bb_recov", False)

        if not rsi_prev_close or not ema200_saved:
            print(f"  [INTRADAY] {ticker}: datos incompletos en data.json — skip")
            continue

        # Fetch precio actual liviano
        current_price = fetch_price_only(sym)
        if current_price is None:
            print(f"  [INTRADAY] {ticker}: no se pudo obtener precio actual — skip")
            continue

        epct_intra = (current_price - ema200_saved) / ema200_saved * 100

        # ── Mismas variables que usa score_signal ────────────────────────────
        _ema_ok_i      = epct_intra >= -5
        _ema_ok_med_i  = epct_intra >= -10
        _div_i         = saved.get("div_bullish", False)
        _rsi10_i       = rsi_prev_close   # RSI del cierre anterior — no intradiario

        # Score con precio actual (EMA recalculada con precio vivo, RSI y BB del cierre)
        _score_i = sum([
            bool(rsi_bounced_15),
            bool(_ema_ok_i or _ema_ok_med_i),
            bool(bb_recov_saved),
        ])

        # ── Condiciones SEÑAL — idénticas al bot diario ──────────────────────
        _senal_normal = (
            _score_i == 3
            and rsi_bounced_15
            and _rsi10_i <= 45
            and epct_intra >= -10   # guardia: precio no se alejó desde el cierre anterior
        )
        _senal_div = (
            _div_i
            and bb_recov_saved
            and (rsi_bounced_15 or _ema_ok_med_i)
            and _score_i >= 2
        )
        signal_still_active = _senal_normal or _senal_div

        # ── Condiciones WATCHLIST — idénticas al bot diario ──────────────────
        _watch_score2 = (
            _score_i == 2
            and not rsi_bounced_15
            and _rsi10_i <= 45
            and _ema_ok_med_i
        )
        # bb_ema_watchlist: RSI <= 40 evita falsos positivos con RSI neutro sobre EMA
        _watch_bb_ema = (
            bb_recov_saved
            and _ema_ok_i
            and not rsi_bounced_15
            and _rsi10_i <= 45
        )
        _watch_div = (
            _div_i
            and _score_i <= 1
            and _rsi10_i <= 45
        )
        watchlist_still_active = _watch_score2 or _watch_bb_ema or _watch_div

        # Si estaba en watchlist y sigue siendo watchlist → skip (ya fue avisado)
        if _intra_in_watchlist and not signal_still_active:
            print(f"  [INTRADAY] {ticker}: watchlist ya enviada hoy, sin upgrade — skip")
            continue
        elif _intra_in_watchlist and signal_still_active:
            print(f"  [INTRADAY] {ticker}: UPGRADE watchlist→señal intradiario")

        print(f"  [INTRADAY] {ticker}: precio=${current_price} EMA200=${ema200_saved} "
              f"({epct_intra:+.1f}%) RSI_cierre={rsi_prev_close} score={_score_i}/3 "
              f"bounced={rsi_bounced_15} div={_div_i} → señal={signal_still_active} watch={watchlist_still_active}")

        if signal_still_active:
            _tv_sym_i  = TV_MAP.get(ticker, ticker)
            _link_tv_i = f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym_i}">Ver gráfico →</a>'

            if not _intra_header_sent:
                send_telegram(
                    f"🔔 CHEQUEO INTRADIARIO — {now_arg().strftime('%H:%M')}\n"
                    f"Señales activas del cierre anterior:"
                )
                _intra_header_sent = True
            # Construir mensaje completo igual al bot diario
            _q_intra = dict(saved)
            _q_intra["price"] = current_price
            _poc_intra = saved.get("poc_proxy") or 1
            _ppct_intra = (current_price - _poc_intra) / _poc_intra * 100
            _fund_intra = FUND.get(ticker, "buenos")
            _score_intra = _score_i
            _rsi_p_intra = saved.get("rsi_prev") or rsi_prev_close
            _analisis_intra = generar_analisis(ticker, _score_intra, _q_intra, epct_intra, _ppct_intra, _fund_intra)
            _suger_intra = sugerencia_signal(_score_intra, rsi_prev_close, epct_intra, _fund_intra,
                                              saved.get("div_bullish", False), bb_recov_saved,
                                              ema_ok=(epct_intra >= -5), ema_ok_media=(epct_intra >= -10))
            _div_note_intra = "\n🔀 <b>Nota:</b> Señal promovida por divergencia alcista." if _q_intra.get("promoted_by_div") else ""
            msg_intra = (
                f"🟢 <b>{ticker} ${current_price:,.2f} — SEÑAL {_score_intra}/3 (Intradiario)</b>\n"
                f"\n<b>Indicadores</b>\n"
                f"📉 {rsi_label_signal(rsi_prev_close, _rsi_p_intra)}\n"
                f"📈 {ema_label_signal(epct_intra, saved.get('emaTrend','lateral'), ema200_saved)}\n"
                f"📦 {poc_label_signal(_ppct_intra, _poc_intra)}\n"
                f"🎢 {bb_label_signal(_q_intra)}\n"
                f"\n🔍 <b>Contexto</b>\n"
                f"{_analisis_intra}\n"
                f"\n💡 <b>Acción</b>\n"
                f"{_suger_intra}"
                f"{_div_note_intra}"
                f"{squeeze_note(_q_intra)}\n"
                f"\n{_link_tv_i}"
            )
            send_telegram_with_button(msg_intra, ticker)
            _intra_fired.append(ticker)
            if ticker not in _daily_intra.get("signals", []):
                _daily_intra.setdefault("signals", []).append(ticker)
            time.sleep(0.3)

        elif watchlist_still_active:
            _tv_sym_iw  = TV_MAP.get(ticker, ticker)
            _link_tv_iw = f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym_iw}">Ver gráfico →</a>'
            if not _intra_header_sent:
                send_telegram(
                    f"🔔 CHEQUEO INTRADIARIO — {now_arg().strftime('%H:%M')}\n"
                    f"Setups en formación:"
                )
                _intra_header_sent = True
            _q_intra_w = dict(saved)
            _q_intra_w["price"] = current_price
            _poc_intra_w = saved.get("poc_proxy") or 1
            _ppct_intra_w = (current_price - _poc_intra_w) / _poc_intra_w * 100
            _fund_intra_w = FUND.get(ticker, "buenos")
            _score_intra_w = _score_i
            _rsi_p_intra_w = saved.get("rsi_prev") or rsi_prev_close
            _analisis_intra_w = generar_analisis(ticker, _score_intra_w, _q_intra_w, epct_intra, _ppct_intra_w, _fund_intra_w)
            _suger_intra_w = sugerencia_watchlist(_score_intra_w, rsi_prev_close, epct_intra, _fund_intra_w,
                                                   saved.get("div_bullish", False), bb_recov_saved,
                                                   saved.get("bb_below", False), rsi_bounced_15)
            msg_intra_w = (
                f"🟡 <b>{ticker} ${current_price:,.2f} — WATCHLIST {_score_intra_w}/3 (Intradiario)</b>\n"
                f"⚠️ <b>Estado:</b> Setup en formación. Aviso previo — monitorear.\n"
                f"\n<b>Indicadores</b>\n"
                f"📉 {rsi_label_watchlist(rsi_prev_close, _rsi_p_intra_w)}\n"
                f"📈 {ema_label_watchlist(epct_intra, saved.get('emaTrend','lateral'))}\n"
                f"📦 {poc_label_watchlist(_ppct_intra_w, _poc_intra_w, current_price)}\n"
                f"🎢 {bb_label_watchlist(_q_intra_w)}\n"
                f"\n🔍 <b>Contexto</b>\n"
                f"{_analisis_intra_w}\n"
                f"\n💡 <b>Acción</b>\n"
                f"{_suger_intra_w}"
                f"{squeeze_note(_q_intra_w)}\n"
                f"\n{_link_tv_iw}"
            )
            send_telegram(msg_intra_w)
            _intra_fired.append(ticker)
            if ticker not in _daily_intra.get("watchlist", []):
                _daily_intra.setdefault("watchlist", []).append(ticker)
            time.sleep(0.3)

    # Guardar daily actualizado
    _dj_intra["daily"] = _daily_intra
    with open("data.json", "w") as f:
        json.dump(_dj_intra, f, indent=2, ensure_ascii=False)

    if not _intra_fired:
        print("[INTRADAY] Sin señales activas en este chequeo.")
    else:
        print(f"[INTRADAY] Alertas enviadas: {', '.join(_intra_fired)}")

    import sys; sys.exit(0)

# ── Fin modo intradiario — continúa el análisis completo diario ───────────────

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
        # Dirección RSI: flecha visual para ver si está tomando carrera o buscando piso
        _rsi_now  = q.get("rsi10") or 50
        _rsi_prev = q.get("rsi_prev") or _rsi_now
        rsi_arrow = "↗️" if _rsi_now > _rsi_prev else ("↘️" if _rsi_now < _rsi_prev else "→")
        q["rsi_direction"] = "subiendo" if _rsi_now > _rsi_prev else ("bajando" if _rsi_now < _rsi_prev else "lateral")
        rsi_direction = q["rsi_direction"]  # ← FIX: extraer a variable local
        print(f"RSI {q['rsi10']}{rsi_arrow} · ${q['price']} · EMA200=${ema200_val} ({epct_debug:+.1f}%){div_tag}{bb_tag}")

        # rsi_bounced_15 ya viene calculado desde fetch_ticker con las últimas 15 velas.
        # No se fusiona con historial previo para evitar falsos positivos de sesiones anteriores.

 # FIX: inicializar rsi_direction antes del bloque fallback como guardia defensiva
    rsi_direction = q.get("rsi_direction", "lateral")
    
    if q.get("_fallback"):
        rsi10 = q["rsi10"] or 50
        _, _, epct, ppct, _, _, _, _, _ = score_signal(ticker, q)
        all_results.append((ticker, 0, q, epct, ppct))
        if rsi10 <= 38:
            radar_info.append((ticker, q, epct, ppct, 0))
        continue

    score, forming, epct, ppct, fund, rsi_bounced, rsi_oversold, ema_ok, ema_ok_media = \
        score_signal(ticker, q)
    all_results.append((ticker, score, q, epct, ppct))

    rsi10 = q["rsi10"] or 50
    # rsi_bounced_15 viene de q (calculado en fetch_ticker), rsi_bounced es 1 vela (fallback)
    rsi_bounced_15 = q.get("rsi_bounced_15", rsi_bounced)

    div      = q.get("div_bullish", False)
    bb_recov = q.get("bb_recov", False)

    # ── Ciclo de Acumulación Inteligente ─────────────────────────────────────
    cyc = get_cycle(ticker)
    is_silenced = cyc["is_silenced"]
    rsi_hit_50  = cyc["rsi_hit_50"]
    rsi_reset   = cyc["rsi_reset"]

    # Fase 2: Detectar cruce RSI > 50 mientras está silenciado
    if is_silenced and not rsi_hit_50 and rsi10 > 50:
        cyc["rsi_hit_50"] = True
        rsi_hit_50 = True
        print(f"  [CICLO] {ticker}: RSI cruzó 50 ({rsi10}) → rsi_hit_50=True")
        save_cycle(ticker, cyc)

    # Fase 2.5: Aviso único para completar media posición
    # Condiciones: posicion=="media" (no avisado aún) + precio cerca EMA + slope > 0.8% + RSI > 50
    # Una vez enviado, posicion pasa a "media_avisado" para no repetir.
    _posicion_actual = cyc.get("posicion", "")
    if is_silenced and _posicion_actual == "media":
        _ema_slope  = q.get("emaSlope", 0.0) or 0.0
        _epct_ciclo = (rsi10 and q.get("ema200")) and ((q["price"] - q["ema200"]) / q["ema200"] * 100) or -99
        _epct_ciclo = (q["price"] - (q.get("ema200") or q["price"])) / (q.get("ema200") or q["price"]) * 100
        dist_ok  = _epct_ciclo >= -10
        trend_ok = _ema_slope > 0.8
        rsi_ok   = rsi10 > 50
        print(f"  [CICLO] {ticker}: media posición — slope={_ema_slope:.3f}% dist={_epct_ciclo:.1f}% rsi={rsi10} → dist_ok={dist_ok} trend_ok={trend_ok} rsi_ok={rsi_ok}")
        if dist_ok and trend_ok and rsi_ok:
            cyc["posicion"] = "media_avisado"
            save_cycle(ticker, cyc)
            _tv_sym_med = TV_MAP.get(ticker, ticker)
            send_telegram(
                f"📈 <b>{ticker}</b> — Considerá completar tu posición\n"
                f"\n"
                f"Tenés <b>media posición</b> abierta. La tendencia confirma fuerza:\n"
                f"• EMA200 con pendiente <b>+{_ema_slope:.2f}%</b> (tendencia alcista sostenida)\n"
                f"• Precio <b>{_epct_ciclo:+.1f}%</b> respecto a EMA200\n"
                f"• RSI(10): <b>{rsi10}</b> — momentum alcista activo\n"
                f"\n"
                f"💡 Si el setup sigue favorable, podés <b>completar a posición completa</b>.\n"
                f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym_med}">Ver gráfico en TradingView →</a>'
            )
            print(f"  [CICLO] {ticker}: aviso 'completar posición' enviado → posicion=media_avisado")

    # Fase 3: RSI_hit_50 confirmado + RSI vuelve a caer bajo 45 → rsi_reset
    if is_silenced and rsi_hit_50 and not rsi_reset and rsi10 < 45:
        cyc["rsi_reset"] = True
        rsi_reset = True
        print(f"  [CICLO] {ticker}: RSI bajó de 45 ({rsi10}) → rsi_reset=True")
        save_cycle(ticker, cyc)

    # Fase 4: rsi_reset activo → despertar automático y devolver al clasificador normal.
    # Ya no se exige rebote+BB aquí: el clasificador evaluará score, watchlist o radar
    # con los indicadores actuales, igual que cualquier activo sin ciclo activo.
    if is_silenced and rsi_reset:
        _posicion_previa = cyc.get("posicion", "completa")
        cyc["is_silenced"] = False
        cyc["rsi_hit_50"]  = False
        cyc["rsi_reset"]   = False
        cyc.pop("posicion", None)
        is_silenced = False
        print(f"  [CICLO] {ticker}: DESPERTAR — ciclo reset completado (posicion_previa={_posicion_previa})")
        save_cycle(ticker, cyc)
        # Notificar despertar con contexto de posicion
        if _posicion_previa in ("media", "media_avisado"):
            if _posicion_previa == "media_avisado":
                send_telegram(
                    f"🔔 <b>{ticker}</b> — Ciclo completado\n"
                    f"Tenés <b>media posición</b> abierta (ya recibiste aviso de completar).\n"
                    f"El activo vuelve al análisis normal — evaluá si la señal justifica acción.\n"
                )
            else:
                send_telegram(
                    f"🔔 <b>{ticker}</b> — Ciclo completado\n"
                    f"Tenés <b>media posición</b> abierta en este activo.\n"
                    f"El activo vuelve al análisis normal — si la señal confirma, "
                    f"podés <b>completar a posición completa</b>.\n"
                )
        else:
            send_telegram(
                f"🔔 <b>{ticker}</b> — Ciclo completado\n"
                f"Posición previa era completa. "
                f"El activo vuelve al análisis normal — si la señal confirma, podés evaluar una <b>nueva entrada</b>.\n"
            )

    # ── Clasificación — condiciones ──────────────────────────────────────────

    # watchlist_score2: score=2, sin rebote RSI, RSI en zona baja, precio no muy lejos de EMA
    watchlist_score2 = (
        score == 2
        and not rsi_bounced_15
        and rsi10 <= 45
        and epct >= -10
    )

    # bb_ema_watchlist: BB recuperado + precio cerca EMA + sin rebote RSI + RSI en zona baja
    # RSI <= 40 evita falsos positivos como GOOGL con RSI 50 sobre EMA
    bb_ema_watchlist = (
        bb_recov
        and epct >= -5
        and not rsi_bounced_15
        and rsi10 <= 45
    )

    # div_to_signal: divergencia bullish + BB + (rebote RSI o precio cerca EMA) + score>=2
    # La divergencia puede reemplazar el rebote RSI como confirmación
    div_to_signal = (
        div
        and bb_recov
        and (rsi_bounced_15 or epct >= -10)
        and score >= 2
    )

    # div_to_watchlist: divergencia con score bajo — setup embrionario a monitorear.
    # RSI <= 35 evita watchlists por divergencia cuando el RSI está simplemente "débil"
    # pero no en zona de oversold real. Activos con RSI 36-45 + div se ignoran.
    div_to_watchlist = div and score <= 1 and rsi10 <= 35

    # Activo silenciado: si llegó acá, aún no completó el reset → ignorado.
    # (El despertar automático ocurre en Fase 4, antes de este bloque)
    if is_silenced:
        print(f"  [CICLO] {ticker}: silenciado — ignorado (RSI={rsi10} hit50={rsi_hit_50} reset={rsi_reset})")
    elif score == 3 and rsi_bounced_15 and rsi10 <= 45:
        q["promoted_by_div"] = False   # señal orgánica, no promovida
        dir_tag = f" {rsi_direction}" if rsi_direction != "lateral" else ""
        print(f"  >>> SEÑAL 3/3: {ticker} rsi={rsi10}{dir_tag} rsi_prev={q.get('rsi_prev')} bb_recov={bb_recov} epct={epct:.1f}")
        signals_found.append((ticker, score, q, epct, ppct, fund))
    elif div_to_signal:
        score = 3
        q["promoted_by_div"] = True
        print(f"  >>> SEÑAL DIV 3/3+div: {ticker} rsi={rsi10} epct={epct:.1f} bb_recov={bb_recov}")
        signals_found.append((ticker, score, q, epct, ppct, fund))
    elif watchlist_score2 or bb_ema_watchlist or div_to_watchlist:
        q["promoted_by_div"] = False   # limpiar flag si no aplica
        reason = "bb_ema" if bb_ema_watchlist else ("div" if div_to_watchlist else "score+rsi")
        print(f"  ... {ticker}: rsi={rsi10} score={score}/3 → watchlist ({reason})")
        watchlist_found.append((ticker, score, q, epct, ppct))
    elif rsi10 <= 35 or (rsi10 < 30 and not rsi_bounced_15):
        q["promoted_by_div"] = False   # limpiar flag si no aplica
        dir_tag = f" {rsi_direction}" if rsi_direction != "lateral" else ""
        print(f"  ... {ticker}: rsi={rsi10}{dir_tag} score={score}/3 → radar")
        radar_info.append((ticker, q, epct, ppct, score))
    else:
        q["promoted_by_div"] = False   # limpiar flag si no aplica
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
_daily = {"date": _today, "signals": [], "watchlist": [], "entradas": []}
try:
    with open("data.json", "r") as f:
        _dj = json.load(f)
    if _dj.get("daily", {}).get("date") == _today:
        _daily = _dj["daily"]
        if "entradas" not in _daily:
            _daily["entradas"] = []
except Exception:
    pass

# ── Skip si ya fue alertado hoy — calculado una vez, antes de los loops ──────
_alerted_signals_full   = set(_daily.get("signals", []))
_alerted_watchlist_full = set(_daily.get("watchlist", []))

# Filtrar signals_found y watchlist_found eliminando los ya alertados
_signals_filtered = []
for _item in signals_found:
    _tk = _item[0]
    _sc = _item[1]; _q2 = _item[2]; _ep2 = _item[3]
    _would_sig = True  # ya clasificó como señal
    if _tk in _alerted_signals_full:
        print(f"  [DAILY] {_tk}: señal ya enviada hoy — skip")
    else:
        _signals_filtered.append(_item)
signals_found = _signals_filtered

_watchlist_filtered = []
for _item in watchlist_found:
    _tk = _item[0]
    if _tk in _alerted_signals_full:
        print(f"  [DAILY] {_tk}: ya en señal hoy — skip watchlist")
    elif _tk in _alerted_watchlist_full:
        print(f"  [DAILY] {_tk}: watchlist ya enviada hoy — skip")
    else:
        _watchlist_filtered.append(_item)
watchlist_found = _watchlist_filtered

# ── 1. Señales confirmadas (Score 3/3) → alerta verde individual ──────────────
_header_sent = False

for ticker, score, q, epct, ppct, fund in signals_found:
    rsi10  = q["rsi10"] or 50
    rsi_p  = q["rsi_prev"] or rsi10
    poc    = q["poc_proxy"] or 0
    div    = q.get("div_bullish", False)
    bb_rec = q.get("bb_recov", False)
    _ema200_s = q.get("ema200") or 1
    _ema_ok_s      = epct >= -5
    _ema_ok_med_s  = epct >= -10

    sugerencia = sugerencia_signal(score, rsi10, epct, fund, div, bb_rec,
                                   ema_ok=_ema_ok_s, ema_ok_media=_ema_ok_med_s)
    analisis   = generar_analisis(ticker, score, q, epct, ppct, fund)

    _tv_sym  = TV_MAP.get(ticker, ticker)
    _link_tv = f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym}">Ver gráfico en TradingView →</a>'

    if not _header_sent:
        send_telegram(session_header)
        time.sleep(0.1)
        _header_sent = True

    _price_fmt = f"${q['price']:,.2f}"
    _div_note = "\n🔀 <b>Nota:</b> Señal promovida por divergencia alcista." if q.get("promoted_by_div") else ""
    msg = (
        f"🟢 <b>{ticker} {_price_fmt} — SEÑAL {score}/3 (Diario)</b>\n"
        f"\n<b>Indicadores</b>\n"
        f"📉 {rsi_label_signal(rsi10, rsi_p)}\n"
        f"📈 {ema_label_signal(epct, q['emaTrend'], q['ema200'])}\n"
        f"📦 {poc_label_signal(ppct, poc)}\n"
        f"🎢 {bb_label_signal(q)}\n"
        f"\n🔍 <b>Contexto</b>\n"
        f"{analisis}\n"
        f"\n💡 <b>Acción</b>\n"
        f"{sugerencia}"
        f"{_div_note}"
        f"{squeeze_note(q)}\n"
        f"\n{_link_tv}"
    )
    print(f"\n{msg}\n")
    send_telegram_with_button(msg, ticker)
    time.sleep(0.2)

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
    rsi_bounced_w = q.get("rsi_bounced_15", (rsi10 > 30 and rsi_p <= 30))

    analisis   = generar_analisis(ticker, score, q, epct, ppct, fund)
    sugerencia = sugerencia_watchlist(score, rsi10, epct, fund, div,
                                      bb_rec, bb_below, rsi_bounced_w)

    _tv_sym_w  = TV_MAP.get(ticker, ticker)
    _link_tv_w = f'📊 <a href="https://www.tradingview.com/chart/?symbol={_tv_sym_w}">Ver gráfico en TradingView →</a>'

    if not _header_sent:
        send_telegram(session_header)
        time.sleep(0.2)
        _header_sent = True

    _price_fmt_w = f"${q['price']:,.2f}"
    msg = (
        f"🟡 <b>{ticker} {_price_fmt_w} — WATCHLIST {score}/3 (Diario)</b>\n"
        f"⚠️ <b>Estado:</b> Setup en formación. Aviso previo — monitorear.\n"
        f"\n<b>Indicadores</b>\n"
        f"📉 {rsi_label_watchlist(rsi10, rsi_p)}\n"
        f"📈 {ema_label_watchlist(epct, q['emaTrend'])}\n"
        f"📦 {poc_label_watchlist(ppct, poc, q['price'])}\n"
        f"🎢 {bb_label_watchlist(q)}\n"
        f"\n🔍 <b>Contexto</b>\n"
        f"{analisis}\n"
        f"\n💡 <b>Acción</b>\n"
        f"{sugerencia}"
        f"{squeeze_note(q)}\n"
        f"\n{_link_tv_w}"
    )
    print(f"\n{msg}\n")
    send_telegram(msg)
    time.sleep(0.2)

    # Acumular en historial del día
    if ticker not in _daily["watchlist"]:
        _daily["watchlist"].append(ticker)

# ── Guardar historial del día + ciclos + quotes ──────────────────────────────
try:
    with open("data.json", "r") as f:
        _dj_full = json.load(f)
except Exception:
    _dj_full = {}
_dj_full["daily"]  = _daily
_dj_full["cycles"] = cycles
# Persistir quotes frescos para que el modo intradiario los lea (incluye promoted_by_div)
_quotes_to_save = {}
for _t, _sc, _q_raw, _ep, _pp in all_results:
    _quotes_to_save[_t] = _q_raw
_dj_full["quotes"] = _quotes_to_save
with open("data.json", "w") as f:
    json.dump(_dj_full, f, indent=2, ensure_ascii=False)

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

    # Sección entradas del día (activos marcados como operados)
    _entradas = _daily.get("entradas", [])
    entradas_section = ""
    if _entradas:
        entradas_lines = ", ".join(f"<b>{e['ticker']}</b> {e['price']} ({e['hora']})" for e in _entradas)
        entradas_section = f"\n\n📌 <b>Entradas del día:</b> {entradas_lines}"

    summary_msg = (
        f"📅 <b>Resumen Diario de Mercado — [{date_str}]</b>\n\n"
        f"Resumen: {intro}"
        f"{entradas_section}"
        f"{radar_section}\n\n"
        f"💡 <b>Nota del Bot:</b> {bot_note}"
    )
    print(f"\n{summary_msg}\n")
    send_telegram(summary_msg)

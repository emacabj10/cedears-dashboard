import json, urllib.request, urllib.error, time, os, random
from datetime import datetime

# ── Configuración (GitHub Secrets) ───────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Diccionarios y Notas (Mantené los tuyos originales) ──────────────────────
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

# ── Funciones de Etiquetas (Usa las que ya tenés en tu archivo) ──────────────
# rsi_label_signal, ema_label_signal, poc_label_signal, etc.

# ── Bucle de Análisis Principal ──────────────────────────────────────────────
all_results = []
signals_found = []
forming_found = []
radar_info = []

for ticker, sym in YF_MAP.items():
    q = fetch_ticker(sym) # Tu función fetch original
    if not q: continue
    
    # Obtenemos el score de tu función score_signal
    score, forming, epct, ppct, fund, poc_max_op, rsi_bounced, rsi_oversold = score_signal(ticker, q)
    all_results.append((ticker, score, q, epct, ppct))

    # ── CLASIFICACIÓN JERÁRQUICA (Sin duplicados) ──
    if score > 2:
        # 1. SEÑAL (Círculo verde si es 4-5, diamante si es 3)
        signals_found.append((ticker, score, q, epct, ppct, fund, poc_max_op))
    
    elif score == 2:
        # 2. WATCHLIST (Solo score 2)
        forming_found.append((ticker, q, epct, ppct, score))
    
    elif (q.get("rsi10") and q["rsi10"] <= 38) or abs(epct) <= 2:
        # 3. RADAR (Solo para el reporte final)
        radar_info.append((ticker, q, epct, ppct, score))

    time.sleep(0.5)

# ── Envío de Mensajes ────────────────────────────────────────────────────────
now_str = datetime.now().strftime("%d/%m %H:%M")

# 1. SEÑALES INDIVIDUALES (🟢/✳️)
for ticker, score, q, epct, ppct, fund, poc_max_op in signals_found:
    emoji = "🟢" if score >= 4 else "✳️"
    size = "Posición completa 100%" if score >= 4 else "Media posición 50%"
    
    msg = (
        f"{emoji} <b>SEÑAL — {ticker} ({score}/5)</b>\n"
        f"📅 {now_str} · Fund: {fund}\n\n"
        f"📉 {rsi_label_signal(q['rsi10'], q['rsi_prev'])}\n"
        f"📈 {ema_label_signal(epct, q['emaTrend'], q['ema200'])}\n"
        f"📊 {poc_label_signal(ppct, q['poc_proxy'])}\n"
        f"🎢 {bb_label_signal(q)}\n\n"
        f"💰 <b>Sugerido: {size}</b>\n"
        f"💵 Precio: ${q['price']:,}"
    )
    send_telegram(msg)
    time.sleep(0.5)

# 2. WATCHLIST INDIVIDUALES (🟡)
for ticker, q, epct, ppct, score in forming_found:
    msg = (
        f"🟡 <b>WATCHLIST — {ticker} ({score}/5)</b>\n"
        f"⚠️ <b>Estado:</b> Setup en formación.\n\n"
        f"📉 {rsi_label_watchlist(q['rsi10'], q['rsi_prev'])}\n"
        f"📈 EMA200 a {epct:+.1f}% de distancia.\n"
        f"📊 POC a {ppct:+.1f}% de distancia.\n\n"
        f"🛑 <b>Acción:</b> NO OPERAR. Esperar rebote o señal > 2."
    )
    send_telegram(msg)
    time.sleep(0.5)

# 3. REPORTE DIARIO (Radar y Resumen)
if radar_info or signals_found or forming_found:
    radar_lines = []
    for ticker, q, epct, ppct, score in radar_info[:6]:
        # Resumen rápido para el radar
        situacion = "RSI bajo" if q['rsi10'] < 35 else "Cerca de EMA"
        radar_lines.append(f"• {ticker}: {situacion} ({q['rsi10']} rsi). Score: {score}/5")
    
    # RSI Promedio
    rsi_values = [res[2]["rsi10"] for res in all_results if res[2].get("rsi10")]
    avg_rsi = round(sum(rsi_values)/len(rsi_values), 1) if rsi_values else 50
    
    msg_reporte = (
        f"📋 <b>Reporte de Mercado — {now_str}</b>\n"
        f"🌡️ RSI Promedio del Panel: {avg_rsi}\n\n"
        f"<b>En el Radar (Seguimiento):</b>\n" + ("\n".join(radar_lines) if radar_lines else "Sin activos en zona.") +
        f"\n\n<i>{random.choice(BOT_NOTES)}</i>"
    )
    send_telegram(msg_reporte)

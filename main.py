from typing import Optional
"""
SupplementsBot - Telegram Medication Reminder Chatbot
Powered by Claude (Anthropic) + python-telegram-bot + APScheduler
"""

import os
import logging
from datetime import date
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import anthropic
from typing import Optional

# ─────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))          # Fallback chat_id (opcional)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ─────────────────────────────────────────────
# Horarios de recordatorio (hora, minuto, etiqueta)
# ─────────────────────────────────────────────
REMINDERS = [
    (9,  0,  "mañana"),
    (12, 30,  "mediodía"),
    (20, 0,  "noche"),
]

# Medicación/vitaminas que debe tomar el usuario — personaliza aquí
MEDICATION_NAME = os.getenv("MEDICATION_NAME", "tus vitaminas y medicación")

# ─────────────────────────────────────────────
# Estado global (en memoria — suficiente para prototipo)
# ─────────────────────────────────────────────
taken_today: dict[str, bool] = {}          # {"2025-01-01_mañana": True, …}
conversation_history: list[dict] = []     # Historial para Claude
registered_chat_id = None  # type: Optional[int]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─────────────────────────────────────────────
# Prompts de sistema
# ─────────────────────────────────────────────
SYSTEM_BASE = f"""Eres SupplementsBot, un asistente que ayuda al usuario \
a recordar tomar {MEDICATION_NAME}.

Normas:
- Habla siempre en español, con tono breve.
- Usa emojis con moderación (1-2 por mensaje).
- Nunca des consejos médicos; solo recordatorios.
- Si el usuario dice que ya tomó el suplemento, celébralo con entusiasmo.
- Si pregunta algo médico, indícale que consulte a su médico."""

SYSTEM_CONFIRM = """
DETECCIÓN DE CONFIRMACIÓN (solo para tu procesamiento interno):
Si el mensaje del usuario indica claramente que YA tomó el suplemento (frases como 
"ya lo tomé", "hecho", "listo", "sí", "tomado", "me lo he tomado", "done", etc.),
añade al final de tu respuesta (en una línea nueva) exactamente:
__CONFIRMADO__:[etiqueta]
donde [etiqueta] es la toma más reciente pendiente según el estado que se te indica.
El usuario NO verá esta línea; solo la usa el sistema.
"""


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def today_key(label: str) -> str:
    return f"{date.today()}_{label}"


def build_status_block() -> str:
    today = date.today()
    lines = [f"Estado de suplementación de hoy ({today.strftime('%d/%m/%Y')}):"]
    for hour, minute, label in REMINDERS:
        icon = "✅" if taken_today.get(today_key(label)) else "⏳"
        lines.append(f"  {icon} {label.capitalize()} ({hour:02d}:{minute:02d})")
    return "\n".join(lines)


def next_pending_label() -> Optional[str]:
    """Returns the label of the most recent reminder that is still pending."""
    for _, _, label in REMINDERS:
        if not taken_today.get(today_key(label)):
            return label
    return None


def normalize_label(raw_label: str) -> Optional[str]:
    aliases = {
        "manana": "mañana",
        "mañana": "mañana",
        "mediodia": "mediodía",
        "mediodía": "mediodía",
        "noche": "noche",
    }
    return aliases.get(raw_label.strip().lower())


def trim_history():
    global conversation_history
    if len(conversation_history) > 30:
        conversation_history = conversation_history[-30:]


# ─────────────────────────────────────────────
# Reminder sender (called by scheduler)
# ─────────────────────────────────────────────
async def send_reminder(app: Application, label: str, force: bool = False):
    key = today_key(label)
    if taken_today.get(key) and not force:
        logger.info(f"Recordatorio de {label} omitido — ya tomada.")
        return

    chat_id = registered_chat_id or CHAT_ID
    if not chat_id:
        logger.warning("No hay chat_id registrado todavía. Envía /start al bot.")
        return

    # Claude genera el texto del recordatorio
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system=SYSTEM_BASE,
        messages=[{
            "role": "user",
            "content": (
                f"Genera un recordatorio breve (máx. 2 frases) y motivador para que "
                f"el usuario tome {MEDICATION_NAME} en la toma de la {label}."
            ),
        }],
    )
    text = response.content[0].text.strip()
    await app.bot.send_message(chat_id=chat_id, text=text)
    logger.info(f"Recordatorio enviado → {label}{' (prueba)' if force else ''}")


# ─────────────────────────────────────────────
# Telegram Handlers
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global registered_chat_id
    registered_chat_id = update.effective_chat.id
    logger.info(f"/start recibido. chat_id={registered_chat_id}")

    times_str = " | ".join(
        f"{h:02d}:{m:02d} ({l})" for h, m, l in REMINDERS
    )
    welcome = (
        f"👋 ¡Hola! Soy *SupplementsBot*, tu recordatorio de {MEDICATION_NAME}.\n\n"
        f"⏰ Te avisaré a las: {times_str}\n\n"
        "Cuando recibas un aviso, escríbeme algo como:\n"
        "  • _\"Ya lo he tomado\"_\n"
        "  • _\"Hecho ✔\"_\n"
        "  • _\"Listo\"_\n\n"
        "y no recibirás más recordatorios para esa toma 😊\n\n"
        "Otros comandos:\n"
        "  /estado — Ver tus tomas de hoy\n"
        "  /resetear — Borrar el estado de hoy\n"
        "  /test_reminder — Enviar un recordatorio de prueba\n"
        "  /ayuda — Más información"
    )
    await update.message.reply_markdown(welcome)


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_status_block())


async def cmd_resetear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = str(date.today())
    keys_cleared = [k for k in taken_today if k.startswith(today)]
    for k in keys_cleared:
        taken_today.pop(k, None)
    await update.message.reply_text(
        f"🔄 Estado de hoy reseteado ({len(keys_cleared)} toma(s) borradas)."
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "🤖 *SupplementsBot — Ayuda*\n\n"
        "/start — Registrarte y ver el resumen\n"
        "/estado — Estado de tus tomas de hoy\n"
        "/resetear — Borrar confirmaciones de hoy\n"
        "/test_reminder [mañana|mediodía|noche] — Enviar un recordatorio de prueba\n"
        "/ayuda — Este mensaje\n\n"
        "_Cualquier otro mensaje será procesado como conversación._"
    )


async def cmd_test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global registered_chat_id

    registered_chat_id = update.effective_chat.id
    label = next_pending_label() or REMINDERS[0][2]
    if context.args:
        parsed_label = normalize_label(" ".join(context.args))
        if not parsed_label:
            valid_labels = ", ".join(label for _, _, label in REMINDERS)
            await update.message.reply_text(
                f"Etiqueta no válida. Usa una de estas: {valid_labels}."
            )
            return
        label = parsed_label

    await send_reminder(context.application, label, force=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global registered_chat_id

    user_text = update.message.text
    registered_chat_id = update.effective_chat.id

    # Añadir al historial
    conversation_history.append({"role": "user", "content": user_text})
    trim_history()

    # Construir sistema completo con contexto actual
    system_full = (
        SYSTEM_BASE
        + "\n\n"
        + build_status_block()
        + "\n"
        + SYSTEM_CONFIRM
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system_full,
        messages=conversation_history,
    )

    raw = response.content[0].text

    # Detectar confirmación oculta
    if "__CONFIRMADO__:" in raw:
        parts = raw.split("__CONFIRMADO__:")
        clean_reply = parts[0].strip()
        tag_line = parts[1].strip().split()[0].lower()

        # Buscar la etiqueta real en nuestros REMINDERS
        matched = next(
            (l for _, _, l in REMINDERS if l in tag_line),
            next_pending_label(),
        )
        if matched:
            taken_today[today_key(matched)] = True
            logger.info(f"Confirmación registrada → {matched}")
    else:
        clean_reply = raw.strip()

    conversation_history.append({"role": "assistant", "content": clean_reply})
    await update.message.reply_text(clean_reply)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("Falta TELEGRAM_TOKEN en el archivo .env")
    if not ANTHROPIC_API_KEY:
        raise ValueError("Falta ANTHROPIC_API_KEY en el archivo .env")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("resetear", cmd_resetear))
    app.add_handler(CommandHandler("test_reminder", cmd_test_reminder))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Scheduler
    scheduler = AsyncIOScheduler()
    for hour, minute, label in REMINDERS:
        scheduler.add_job(
            send_reminder,
            trigger="cron",
            hour=hour,
            minute=minute,
            args=[app, label],
            id=f"reminder_{label}",
            replace_existing=True,
        )
    scheduler.start()
    logger.info(
        "Scheduler activo. Recordatorios programados: "
        + ", ".join(f"{h:02d}:{m:02d}" for h, m, _ in REMINDERS)
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

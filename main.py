"""
SupplementsBot - Telegram Medication Reminder Chatbot
Powered by Claude (Anthropic) + python-telegram-bot + APScheduler
"""

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
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
from reminders import REMINDERS

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
REMINDER_TIMEZONE = os.getenv("REMINDER_TIMEZONE", "Europe/Madrid")

try:
    BOT_TZ = ZoneInfo(REMINDER_TIMEZONE)
except ZoneInfoNotFoundError:
    logger.warning(
        f"Zona horaria inválida '{REMINDER_TIMEZONE}'. Usando Europe/Madrid."
    )
    BOT_TZ = ZoneInfo("Europe/Madrid")

# ─────────────────────────────────────────────
# Horarios de recordatorio (hora, minuto, etiqueta)
# ─────────────────────────────────────────────

# Medicación/vitaminas que debe tomar el usuario — personaliza aquí
MEDICATION_NAME = os.getenv("MEDICATION_NAME", "tus vitaminas y medicación")

# ─────────────────────────────────────────────
# Estado global (en memoria — suficiente para prototipo)
# ─────────────────────────────────────────────
dose_taken: dict[str, str] = {}            # {"2025-01-01": "09:32"} — hora de confirmación
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
- Es una única toma diaria. Si el usuario la confirma, celebra con entusiasmo.
- Una vez confirmada la toma, ya no quedará ningún recordatorio pendiente ese día.
- Si pregunta algo médico, indícale que consulte a su médico."""

SYSTEM_CONFIRM = """
DETECCIÓN DE CONFIRMACIÓN (solo para tu procesamiento interno):
Si el mensaje del usuario indica claramente que YA tomó el suplemento (frases como
"ya lo tomé", "hecho", "listo", "sí", "tomado", "me lo he tomado", "done", etc.),
añade al final de tu respuesta (en una línea nueva) exactamente:
__CONFIRMADO__
El usuario NO verá esta línea; solo la usa el sistema.
"""


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def today_dose_key() -> str:
    return str(datetime.now(BOT_TZ).date())


def is_dose_taken() -> bool:
    return bool(dose_taken.get(today_dose_key()))


def get_dose_taken_time() -> Optional[str]:
    """Returns the HH:MM when the dose was confirmed today, or None."""
    return dose_taken.get(today_dose_key())


def mark_dose_taken() -> None:
    dose_taken[today_dose_key()] = datetime.now(BOT_TZ).strftime("%H:%M")


def build_status_block() -> str:
    today = datetime.now(BOT_TZ).date()
    taken_time = get_dose_taken_time()
    if taken_time:
        icon, status = "✅", f"tomada a las {taken_time}"
    else:
        icon, status = "⏳", "pendiente"
    reminder_times = ", ".join(f"{h:02d}:{m:02d}" for h, m, _ in REMINDERS)
    return (
        f"Estado del día ({today.strftime('%d/%m/%Y')}):\n"
        f"  {icon} Toma diaria: {status}\n"
        f"  ⏰ Avisos programados: {reminder_times}"
    )


def current_reminder_label() -> str:
    """Returns the label of the most recently triggered reminder slot."""
    now = datetime.now(BOT_TZ)
    label = REMINDERS[0][2]
    for h, m, lbl in REMINDERS:
        if (now.hour, now.minute) >= (h, m):
            label = lbl
    return label


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
    if len(conversation_history) >5:
        conversation_history = conversation_history[-5:]


# ─────────────────────────────────────────────
# Reminder sender (called by scheduler)
# ─────────────────────────────────────────────
async def send_reminder(app: Application, label: str, force: bool = False):
    if is_dose_taken() and not force:
        logger.info(f"Recordatorio de {label} omitido — toma diaria ya confirmada.")
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
        f"👋 ¡Hola! Soy SupplementsBot, tu recordatorio de {MEDICATION_NAME}.\n\n"
        f"⏰ Te avisaré a las: {times_str}\n"
        "Si no confirmas, te reenviaré el aviso en la siguiente hora programada.\n\n"
        "Cuando recibas un aviso, escríbeme algo como:\n"
        '  • "Ya lo he tomado"\n'
        '  • "Hecho ✔"\n'
        '  • "Listo"\n\n'
        "y no recibirás más avisos en todo el día 😊\n\n"
        "Otros comandos:\n"
        "  /estado — Ver el estado de hoy\n"
        "  /resetear — Borrar la confirmación de hoy\n"
        "  /test_reminder — Enviar un recordatorio de prueba\n"
        "  /ayuda — Más información"
    )
    await update.message.reply_text(welcome)


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_status_block())


async def cmd_resetear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    was_taken = dose_taken.pop(today_dose_key(), None)
    msg = "🔄 Toma del día reseteada." if was_taken else "No había ninguna toma registrada hoy."
    await update.message.reply_text(msg)


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 SupplementsBot — Ayuda\n\n"
        "/start — Registrarte y ver el resumen\n"
        "/estado — Estado de tus tomas de hoy\n"
        "/resetear — Borrar confirmaciones de hoy\n"
        "/test_reminder [mañana|mediodía|noche] — Enviar un recordatorio de prueba\n"
        "/ayuda — Este mensaje\n\n"
        "Cualquier otro mensaje será procesado como conversación."
    )


async def cmd_test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global registered_chat_id

    registered_chat_id = update.effective_chat.id
    label = current_reminder_label()
    if context.args:
        parsed_label = normalize_label(" ".join(context.args))
        if not parsed_label:
            valid_labels = ", ".join(lbl for _, _, lbl in REMINDERS)
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
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=system_full,
        messages=conversation_history,
    )

    raw = response.content[0].text

    # Detectar confirmación oculta
    if "__CONFIRMADO__" in raw:
        clean_reply = raw.split("__CONFIRMADO__")[0].strip()
        mark_dose_taken()
        logger.info("Toma diaria confirmada.")
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
    scheduler = AsyncIOScheduler(timezone=BOT_TZ)
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
    logger.info(f"Zona horaria de recordatorios: {BOT_TZ}")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

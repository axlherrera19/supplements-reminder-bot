"""
SuplementaBot - Telegram Medication Reminder Chatbot
Powered by Claude (Anthropic) + python-telegram-bot + APScheduler
"""

import os
import logging
import json
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import claude_service
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

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))          # Fallback chat_id (opcional)
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
STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")

# ─────────────────────────────────────────────
# Estado global (en memoria — suficiente para prototipo)
# ─────────────────────────────────────────────
dose_taken: dict[str, str] = {}            # {"2025-01-01": "09:32"} — hora de confirmación
conversation_history: list[dict] = []     # Historial para Claude
registered_chat_id = None  # type: Optional[int]


def save_state() -> None:
    state = {
        "dose_taken": dose_taken,
        "registered_chat_id": registered_chat_id,
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError as e:
        logger.warning(f"No se pudo guardar el estado en {STATE_FILE}: {e}")


def load_state() -> None:
    global registered_chat_id
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if isinstance(state.get("dose_taken"), dict):
            dose_taken.update(
                {
                    str(k): str(v)
                    for k, v in state["dose_taken"].items()
                    if isinstance(k, str) and isinstance(v, str)
                }
            )
        saved_chat_id = state.get("registered_chat_id")
        if isinstance(saved_chat_id, int):
            registered_chat_id = saved_chat_id
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"No se pudo cargar el estado desde {STATE_FILE}: {e}")


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
    save_state()


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text


def user_confirms_dose(text: str) -> bool:
    normalized = normalize_text(text)

    negative_markers = [
        "no la he tomado",
        "no lo he tomado",
        "aun no",
        "todavia no",
        "aun no la tomo",
        "aun no lo tomo",
        "todavia no la tomo",
        "todavia no lo tomo",
    ]
    if any(marker in normalized for marker in negative_markers):
        return False

    confirmation_phrases = [
        "ya lo tome",
        "ya la tome",
        "me lo tome",
        "me la tome",
        "lo he tomado",
        "la he tomado",
        "tomado",
        "hecho",
        "listo",
        "ok tomado",
        "dosis tomada",
        "ya esta",
        "done",
    ]
    return any(phrase in normalized for phrase in confirmation_phrases)


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

    text = claude_service.generate_reminder(label)
    await app.bot.send_message(chat_id=chat_id, text=text)
    logger.info(f"Recordatorio enviado → {label}{' (prueba)' if force else ''}")


# ─────────────────────────────────────────────
# Telegram Handlers
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global registered_chat_id
    registered_chat_id = update.effective_chat.id
    save_state()
    logger.info(f"/start recibido. chat_id={registered_chat_id}")

    times_str = " | ".join(
        f"{h:02d}:{m:02d} ({l})" for h, m, l in REMINDERS
    )
    welcome = (
        f"👋 ¡Hola! Soy SuplementaBot, tu recordatorio de {MEDICATION_NAME}.\n\n"
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
    if was_taken:
        save_state()
    msg = "🔄 Toma del día reseteada." if was_taken else "No había ninguna toma registrada hoy."
    await update.message.reply_text(msg)


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 SuplementaBot — Ayuda\n\n"
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
    save_state()

    # Confirmación determinista local para no depender del formato del modelo.
    if user_confirms_dose(user_text):
        if is_dose_taken():
            taken_time = get_dose_taken_time()
            already_msg = (
                f"✅ Ya la habías confirmado hoy (a las {taken_time}). "
                "No te volveré a recordar la toma de hoy."
            )
            await update.message.reply_text(already_msg)
            return

        mark_dose_taken()
        logger.info("Toma diaria confirmada por detector local.")
        await update.message.reply_text(
            "🎉 Perfecto, toma de hoy confirmada. "
            "No te enviaré más recordatorios hasta mañana."
        )
        return

    # Añadir al historial
    conversation_history.append({"role": "user", "content": user_text})
    trim_history()
    
    raw = claude_service.process_user_message(conversation_history, build_status_block())
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

    load_state()

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
    logger.info(f"Estado persistido en: {STATE_FILE}")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

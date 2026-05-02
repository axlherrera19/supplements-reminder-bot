import anthropic
import os
import logging
from dotenv import load_dotenv

from prompts import SYSTEM_BASE, MEDICATION_NAME

load_dotenv()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)



def generate_reminder(label: str) -> str:
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
    return response.content[0].text.strip()

def process_user_message(conversation_history: list[dict], status_block: str) -> str:
    # Construir sistema completo con contexto actual
    system_full = (
        SYSTEM_BASE
        + "\n\n"
        + status_block
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=system_full,
        messages=conversation_history,
    )

    raw = response.content[0].text
    return raw.strip()

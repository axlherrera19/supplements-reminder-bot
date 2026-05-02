# 💊 SuplementaBot — Recordatorio de medicación con IA

Bot de Telegram impulsado por Claude (Anthropic) que te recuerda tomar tu medicación
o vitaminas **2-3 veces al día** y entiende cuando le confirmas que ya lo has hecho.

## ✅ Cambio relevante (mayo 2026)

Se ha reforzado la lógica para evitar falsos positivos y estados inconsistentes:

- La confirmación de toma ahora se detecta en backend con reglas locales (no depende de una marca oculta en la respuesta del modelo).
- El estado diario ya no vive solo en memoria: se persiste en disco en un archivo JSON.
- `/estado` y el envío/omisión de recordatorios usan la misma fuente de estado persistido.

Con esto se corrigen estos síntomas:

- Mensajes tipo "ya habías confirmado" cuando realmente no se había confirmado.
- Nuevos recordatorios después de haber confirmado la toma.
- `/estado` mostrando pendiente pese a haber confirmado.

---

## 🚀 Configuración en 5 pasos

### 1. Crear el bot en Telegram

1. Abre Telegram y busca **@BotFather**
2. Escribe `/newbot` y sigue las instrucciones
3. Copia el **token** que te entrega (formato: `123456789:ABC-DEF...`)
4. **Importante**: Envia un primer mensaje a este chat, esto generará un id que será importante en el siguiente paso.

### 2. Obtener tu Chat ID

1. Busca **@@RawDataBot** en Telegram
2. Escribe `/start` — te mostrará tu `id` numérico
3. Copia ese id

### 3. Obtener la API key de Anthropic

- Ve a https://console.anthropic.com → *API Keys* → *Create Key*

### 4. Configurar el archivo `.env`

```bash
cp .env.example .env
# Edita .env con tus valores reales
```

```env
TELEGRAM_TOKEN=tu_token_aqui
CHAT_ID=tu_chat_id_aqui
ANTHROPIC_API_KEY=tu_api_key_aqui
MEDICATION_NAME=vitamina D y omega-3   # Personaliza esto
REMINDER_TIMEZONE=Europe/Madrid         # Horario de recordatorios (IANA tz)
STATE_FILE=bot_state.json               # Archivo de estado persistido
```

Si tu servidor está en UTC (por ejemplo en EC2), deja `REMINDER_TIMEZONE=Europe/Madrid`
para que las horas de `REMINDERS` se interpreten en horario de España (incluyendo DST).

### 5. Instalar y ejecutar

```bash
# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Instalar dependencias
pip install -r requirements.txt

# Lanzar el bot
python main.py
```

---

## 📱 Uso

| Acción | Cómo |
|---|---|
| Iniciar el bot | Envía `/start` al bot en Telegram |
| Ver estado de hoy | `/estado` |
| Resetear confirmaciones | `/resetear` |
| Enviar un reminder de prueba | `/test_reminder` o `/test_reminder noche` |
| Confirmar que tomaste la medicación | Escribe algo como: *"Ya lo hice"*, *"Hecho"*, *"Listo ✔"* |
| Conversar libremente | Cualquier mensaje — Claude responderá en contexto |

---

## ⏰ Horarios por defecto

| Toma | Hora |
|---|---|
| 🌅 Mañana | 09:00 |
| ☀️ Mediodía | 12:30 |
| 🌙 Noche | 20:00 |

Para cambiarlos, edita la lista `REMINDERS` en `reminders.py`:

```python
REMINDERS = [
    (9,  0,  "mañana"),    # (hora, minuto, etiqueta)
    (22, 30, "noche"),
]
```

---

## 🏗️ Arquitectura

```
main.py
│
├── APScheduler  ──► send_reminder()  ──► Claude genera texto ──► Telegram
│
└── python-telegram-bot
    ├── /start     ──► registra chat_id
    ├── /estado    ──► muestra tomas de hoy
    ├── /resetear  ──► borra estado del día
    └── handle_message() ──► detector local confirma toma + Claude conversa
```

**Lógica de confirmación:**
La confirmación de toma se decide en backend con reglas locales sobre el texto
del usuario (por ejemplo: "ya lo tomé", "hecho", "listo"). Si se confirma,
se marca la dosis del día y no se envían más recordatorios ese día.

Claude sigue generando recordatorios y conversación, pero ya no decide el estado
de confirmación del sistema.

---

## 🔒 Notas de seguridad

- El estado se guarda en `STATE_FILE` (por defecto `bot_state.json`).
- Si reinicias el proceso en la misma máquina y el archivo existe, el estado se conserva.
- Si ejecutas en Docker/ECS/EC2 con reemplazo de contenedor/instancia sin volumen persistente,
  el estado se perderá. En ese caso, monta un volumen o usa SQLite/Redis.
- Añade `.env` a tu `.gitignore` — nunca subas tus tokens a Git.

## 🐳 Ejecución continua (opcional)

Para que el bot corra 24/7 en un servidor, puedes usar `systemd`, `supervisor`,
o simplemente Docker:

```bash
# Con nohup (quick & dirty)
nohup python main.py > supplements_bot.log 2>&1 &
```

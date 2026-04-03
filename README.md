# 💊 SupplementsBot — Recordatorio de medicación con IA

Bot de Telegram impulsado por Claude (Anthropic) que te recuerda tomar tu medicación
o vitaminas **2-3 veces al día** y entiende cuando le confirmas que ya lo has hecho.

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
    └── handle_message() ──► Claude procesa + detecta confirmación
```

**Lógica de confirmación:**
Claude recibe el contexto del estado actual y detecta si el mensaje del usuario
confirma que ya tomó la medicación. Si es así, marca esa toma como completada
y no se enviarán más recordatorios para ese dia.

---

## 🔒 Notas de seguridad

- El estado se guarda **en memoria** (se pierde al reiniciar). Para producción,
  usa una base de datos (SQLite, Redis, etc.).
- Añade `.env` a tu `.gitignore` — nunca subas tus tokens a Git.

## 🐳 Ejecución continua (opcional)

Para que el bot corra 24/7 en un servidor, puedes usar `systemd`, `supervisor`,
o simplemente Docker:

```bash
# Con nohup (quick & dirty)
nohup python main.py > supplements_bot.log 2>&1 &
```

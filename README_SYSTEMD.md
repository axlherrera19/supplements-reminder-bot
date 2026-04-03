```
[Unit]
Description=Supplements Reminder Bot Telegram
After=network.target

[Service]
WorkingDirectory=/home/ec2-user/supplements-reminder-bot
ExecStart=/home/ec2-user/supplements-reminder-bot/venv/bin/python main.py
Restart=always
EnvironmentFile=/home/ec2-user/supplements-reminder-bot/.env

[Install]
WantedBy=multi-user.target
```


# 1. Crear el fichero
sudo nano /etc/systemd/system/supplements-bot.service
# 2. Recargar systemd para que detecte el nuevo servicio
sudo systemctl daemon-reload
# 3. Activarlo para que arranque automáticamente al reiniciar
sudo systemctl enable supplements-bot
# 4. Arrancarlo ahora
sudo systemctl start supplements-bot
# 5. Verificar que está corriendo
sudo systemctl status supplements-bot


# Ver los logs en directo
sudo journalctl -u supplements-bot -f
.PHONY: help build up down restart logs logs-app logs-mongo ps clean fclean run api install mongo-shell dashboard

COMPOSE = docker compose

# ─── AYUDA ────────────────────────────────────────────────────────────────────
help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ─── DOCKER COMPOSE ───────────────────────────────────────────────────────────
build: ## Construye la imagen de la app
	$(COMPOSE) build

up: ## Levanta todos los servicios en segundo plano
	$(COMPOSE) up -d --build

down: ## Para y elimina los contenedores
	$(COMPOSE) down

restart: ## Reinicia todos los servicios
	$(COMPOSE) restart

logs: ## Muestra logs de todos los servicios (en vivo)
	$(COMPOSE) logs -f

logs-app: ## Muestra logs solo del servicio app
	$(COMPOSE) logs -f app

ps: ## Lista el estado de los contenedores
	$(COMPOSE) ps

clean: ## Para contenedores y elimina volúmenes
	$(COMPOSE) down -v

fclean: ## Para contenedores, elimina volúmenes e imágenes construidas
	$(COMPOSE) down -v --rmi local

# ─── APP LOCAL ────────────────────────────────────────────────────────────────
install: ## Instala las dependencias Python
	pip install -r requirements.txt

run: ## Ejecuta main.py directamente (entorno local)
	python main.py


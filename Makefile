.PHONY: help install dev prod clean docker-up docker-down docker-logs


# --- Variables ---
VENV           := .venv
PIP            := $(VENV)/bin/pip
PYTHON         := $(VENV)/bin/python
EXEC_SCRIPT    := ./exec


# --- Default ---
help:
	@echo "Vion AI Bot - Development & Operations"
	@echo "--------------------------------------------------------"
	@echo "Environment Setup:"
	@echo "  make install      - Install standard Python dependencies"
	@echo "  make clean        - Remove cache files, compiled bytecodes, and temp files"
	@echo ""
	@echo "Execution:"
	@echo "  make dev          - Start the bot with no supervisor or installs"
	@echo "  make prod         - Start the bot with supervisor loop and installs"


# --- Environment ---
install:
	$(PIP) install -r requirements.txt

clean:
	@echo "Sweeping up caches..."
	@find . -type d -name "__pycache__" -exec rm -rfv {} +
	@find . -type f -name "*.pyc" -print -delete
	@rm -rfv .pytest_cache
	@echo "Clean complete."


# --- Execution ---
dev:
	@chmod +x $(EXEC_SCRIPT)
	$(EXEC_SCRIPT) --check

prod:
	@chmod +x $(EXEC_SCRIPT)
	$(EXEC_SCRIPT) --check --supervise --install

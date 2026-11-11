PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install test lint format run web demo browsers clean-cache

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[web,browser,google,dev]"

browsers:
	$(BIN)/playwright install chromium

test:
	$(BIN)/python -m pytest -q

lint:
	$(BIN)/ruff check .
	$(BIN)/mypy hirelane

format:
	$(BIN)/ruff check --fix .

run:
	$(BIN)/hirelane run

web:
	$(BIN)/hirelane web

demo:
	$(BIN)/hirelane demo

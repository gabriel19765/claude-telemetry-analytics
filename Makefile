.PHONY: build run test api dev clean help

help:
	@echo "Claude Code Telemetry Platform — Developer Commands"
	@echo "---------------------------------------------------"
	@echo "make build    Build Docker image"
	@echo "make run      Start platform with Docker Compose"
	@echo "make test     Run pytest test suite"
	@echo "make ingest   Run ingestion pipeline locally"
	@echo "make api      Run FastAPI server locally on port 8000"
	@echo "make dashboard Run Streamlit dashboard locally on port 8501"
	@echo "make skill    Test agent skill CLI"

build:
	docker compose build

run:
	docker compose up

test:
	pytest tests/ -v

ingest:
	python3 -m src.ingestion

api:
	python3 -m uvicorn src.api:app --reload --port 8000

dashboard:
	streamlit run src/app.py

skill:
	python3 agent/skills/telemetry_analyzer.py --tables

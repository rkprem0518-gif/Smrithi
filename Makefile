# Smriti task runner for Linux/macOS.  make setup | demo | test | lint | create-agent | dry-run | check | call PHONE=+91... | seed
PY := .venv/bin/python

.PHONY: setup demo test lint create-agent dry-run check call seed

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt
	test -f .env || cp .env.example .env

demo:
	$(PY) -m uvicorn app.main:app --reload

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

create-agent:
	$(PY) scripts/create_agent.py

dry-run:
	$(PY) scripts/create_agent.py --dry-run

check:
	$(PY) scripts/check_live.py

call:
	@test -n "$(PHONE)" || (echo "Usage: make call PHONE=+91XXXXXXXXXX" && exit 1)
	$(PY) scripts/test_call.py $(PHONE)

seed:
	$(PY) scripts/seed_demo.py

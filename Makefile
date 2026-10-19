PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: test run install demo-check

install:
	$(PYTHON) -m pip install --requirement requirements.lock

test:
	$(PYTHON) -m pytest

demo-check:
	$(PYTHON) -m scripts.demo_smoke

run:
	$(PYTHON) app.py

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: test run install

install:
	$(PYTHON) -m pip install --requirement requirements.lock

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) app.py

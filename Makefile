PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest
PYTHONPATH ?= src
CSV ?= samples/watchlist_with_header.csv

export PYTHONPATH

.PHONY: lint test run

lint:
	$(PYTHON) -m compileall src

test:
	$(PYTEST)

run:
	$(PYTHON) src/app.py --csv $(CSV)

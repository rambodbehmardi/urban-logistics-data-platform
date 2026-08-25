PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH

.PHONY: demo test safety compile check clean

demo:
	$(PYTHON) -m urban_data_platform demo --output-dir build/raw --db build/platform.db --reset

test:
	$(PYTHON) -m unittest discover -s tests -v

safety:
	$(PYTHON) scripts/public_safety_scan.py .

compile:
	$(PYTHON) -m compileall -q src tests scripts

check: compile test demo safety

clean:
	$(PYTHON) -m urban_data_platform clean --output-dir build

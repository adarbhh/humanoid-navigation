SHELL       := /bin/bash
ENV         := robotics-assignment
PYTHON      := conda run -n $(ENV) python
SEED        ?= 42

# ── Setup ──────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	bash setup.sh

# ── Generate maze (standalone) ─────────────────────────────────────────────
.PHONY: maze
maze:
	$(PYTHON) -m maze.generator --seed $(SEED) --grid-size 10 --out /tmp/maze_$(SEED)
	@echo "Maze written to /tmp/maze_$(SEED)/"

# ── Run a single navigation episode ────────────────────────────────────────
.PHONY: run
run:
	$(PYTHON) runner.py --seed $(SEED)

# ── Batch KPI run (N=20 held-out seeds) ────────────────────────────────────
.PHONY: batch
batch:
	$(PYTHON) batch_runner.py --seeds-file seeds/held_out.txt --workers 4

# ── Generate KPI report ────────────────────────────────────────────────────
.PHONY: report
report:
	$(PYTHON) -m nbconvert --to html --execute analysis/report.ipynb \
	    --output analysis/report.html
	@echo "Report written to analysis/report.html"

# ── Live demo (the money shot) ─────────────────────────────────────────────
.PHONY: demo
demo:
	$(PYTHON) demo.py --seed $(SEED)

# ── Tests ──────────────────────────────────────────────────────────────────
.PHONY: test
test:
	$(PYTHON) -m pytest tests/ -v

.PHONY: test-phase1
test-phase1:
	$(PYTHON) tests/test_phase1_setup.py

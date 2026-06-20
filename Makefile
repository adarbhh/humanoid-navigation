SHELL       := /bin/bash
ENV         := robotics-assignment
PYTHON      := conda run -n $(ENV) python
SEED        ?= 42
SPEED       ?= 2.0

# ── Setup ──────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	bash setup.sh

# ── Generate maze (standalone) ─────────────────────────────────────────────
.PHONY: maze
maze:
	$(PYTHON) -m maze.generator --seed $(SEED) --grid-size 10
	@echo "Maze written to mazes/seed$(SEED)_size10/"

# ── Run a single navigation episode ────────────────────────────────────────
.PHONY: run
run:
	$(PYTHON) runner.py --seed $(SEED)

# ── Run episode with data recording ────────────────────────────────────────
.PHONY: record
record:
	$(PYTHON) runner.py --seed $(SEED) --record

# ── Batch KPI run (25 held-out seeds) ──────────────────────────────────────
.PHONY: batch
batch:
	$(PYTHON) scripts/batch_eval.py --seeds seeds/held_out.txt

# ── Generate KPI report ────────────────────────────────────────────────────
.PHONY: report
report:
	$(PYTHON) report/generate_report.py
	@echo "Report written to report/kpi_report.html"

# ── Live demo (the money shot) ─────────────────────────────────────────────
.PHONY: demo
demo:
	$(PYTHON) runner.py --seed $(SEED) --speed $(SPEED) --demo

# ── Dijkstra planner demo ──────────────────────────────────────────────────
.PHONY: demo-dijkstra
demo-dijkstra:
	$(PYTHON) runner.py --seed $(SEED) --speed $(SPEED) --planner dijkstra --demo

# ── Compare planners (A* vs Dijkstra) ──────────────────────────────────────
.PHONY: compare-planners
compare-planners:
	$(PYTHON) scripts/compare_planners.py --seed $(SEED) --no-viz

# ── Dynamic obstacle demo ─────────────────────────────────────────────────
.PHONY: demo-dynamic
demo-dynamic:
	$(PYTHON) runner_dynamic.py --seed $(SEED) --speed $(SPEED) --demo

# ── Fault injection demo ───────────────────────────────────────────────────
.PHONY: demo-fault
demo-fault:
	$(PYTHON) runner_fault.py --seed $(SEED) --speed $(SPEED) --demo

# ── Tests ──────────────────────────────────────────────────────────────────
.PHONY: test
test:
	$(PYTHON) -m pytest tests/ -v

.PHONY: test-phase1
test-phase1:
	$(PYTHON) tests/test_phase1_setup.py

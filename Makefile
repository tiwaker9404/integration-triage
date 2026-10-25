.PHONY: install test eval demo

install:
	pip install -e ".[dev]"

test:
	pytest -q

eval:
	triage eval --check

demo:
	triage diagnose --logs examples/outage.jsonl --ticket-file examples/outage.ticket.txt

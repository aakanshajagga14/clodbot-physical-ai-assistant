.PHONY: dev test

dev:
	./run_clodbot.sh

test:
	.venv/bin/python -m pytest
	cd frontend && /Users/aakanshajagga/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --test tests/rendered-html.test.mjs

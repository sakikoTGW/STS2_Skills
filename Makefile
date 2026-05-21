.PHONY: install dev test lint sync-version check-version

install:
	pip install -e ".[mcp]"

dev:
	pip install -e ".[mcp,dev]"

test: dev
	pytest
	python tests/test_repo_meta.py

lint: dev
	ruff check plugins/sts2 scripts tests

sync-version:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync-version.ps1

check-version:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync-version.ps1 -Check

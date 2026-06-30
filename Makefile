# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
.PHONY: install test check run build up down

install:
	python -m pip install -e '.[dev,ml]'

test:
	python -m pytest -q

check:
	python -m compileall -q backend clients ml tools tests
	python -m pytest -q

run:
	python -m uvicorn backend.app.main:app --reload

build:
	docker build -t hcp-xml-workflow-chat:local .

up:
	docker compose up --build

down:
	docker compose down


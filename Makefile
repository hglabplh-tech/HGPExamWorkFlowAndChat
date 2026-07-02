# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
.PHONY: install test check run build up down client-bundle client-android-sync client-ios-sync client-macos-dmg-silicon client-macos-dmg-intel client-macos-dmg-universal client-windows-build

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
	docker build -t hgp-exam-work-flow-and-chat:local .

up:
	docker compose up --build

down:
	docker compose down

client-bundle:
	python tools/build_client_bundle.py --api-base "$${HCP_API_BASE:-}"

client-android-sync:
	cd clients/native && npm run android:sync

client-ios-sync:
	cd clients/native && npm run ios:sync

client-macos-dmg-silicon:
	cd clients/native && npm run macos:build:silicon

client-macos-dmg-intel:
	cd clients/native && npm run macos:build:intel

client-macos-dmg-universal:
	cd clients/native && npm run macos:build:universal

client-windows-build:
	cd clients/native && npm run windows:build

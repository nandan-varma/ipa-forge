# Common developer tasks. Usage: make <target>
#   make test    — full test suite with coverage (fail < 80%)
#   make lint    — ruff check
#   make type    — mypy
#   make format  — ruff format
#   make gui     — launch the novice web GUI
#   make dry-patch APP=<app> IPA=path/to/App.ipa — hooks-gate dry-run against patches/<app>/<app>.yaml
#   make build-dylib APP=<app> — rebuild patches/<app>/dylib/'s hook dylib

.PHONY: test lint type format check gui dry-patch build-dylib

# No default: each developer's source IPA lives at a different local path,
# and APP selects which patches/<app>/ directory to use.
# Pass both on the command line, e.g. `make dry-patch APP=myapp IPA=~/ipa/App.ipa`.
APP :=
IPA :=

test:
	python3 -m pytest tests/ -q

lint:
	ruff check .

type:
	mypy ipa_forge/

format:
	ruff format .

check: lint type
	python3 -m pytest tests/ -q

gui:
	forge gui

dry-patch:
	@test -n "$(APP)" || { echo "usage: make dry-patch APP=<app> IPA=path/to/App.ipa" >&2; exit 1; }
	@test -n "$(IPA)" || { echo "usage: make dry-patch APP=<app> IPA=path/to/App.ipa" >&2; exit 1; }
	forge patch --ipa $(IPA) --patches patches/$(APP)/$(APP).yaml --output /tmp/dry.ipa --dry-run

build-dylib:
	@test -n "$(APP)" || { echo "usage: make build-dylib APP=<app>" >&2; exit 1; }
	patches/$(APP)/dylib/build.sh

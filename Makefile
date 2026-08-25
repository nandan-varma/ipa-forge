# Common developer tasks. Usage: make <target>
#   make test    — full test suite with coverage (fail < 80%)
#   make lint    — ruff check
#   make type    — mypy
#   make format  — ruff format
#   make gui     — launch the novice web GUI
#   make dry-youtube YOUTUBE_IPA=path/to/App.ipa — hooks-gate dry-run
#   make dry-spotify SPOTIFY_IPA=path/to/App.ipa — hooks-gate dry-run
#   make build-youtube / build-spotify — rebuild the hook dylibs

.PHONY: test lint type format check gui dry-youtube dry-spotify build-youtube build-spotify

# No default: each developer's source IPA lives at a different local path.
# Pass it on the command line, e.g. `make dry-youtube YOUTUBE_IPA=~/ipa/App.ipa`.
YOUTUBE_IPA :=
SPOTIFY_IPA :=

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

dry-youtube:
	@test -n "$(YOUTUBE_IPA)" || { echo "usage: make dry-youtube YOUTUBE_IPA=path/to/App.ipa" >&2; exit 1; }
	forge patch --ipa $(YOUTUBE_IPA) --patches patches/youtube/youtube.yaml --output /tmp/dry.ipa --dry-run

dry-spotify:
	@test -n "$(SPOTIFY_IPA)" || { echo "usage: make dry-spotify SPOTIFY_IPA=path/to/App.ipa" >&2; exit 1; }
	forge patch --ipa $(SPOTIFY_IPA) --patches patches/spotify/spotify.yaml --output /tmp/dry.ipa --dry-run

build-youtube:
	patches/youtube/dylib/build.sh

build-spotify:
	patches/spotify/dylib/build.sh

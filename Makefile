# Common developer tasks. Usage: make <target>
#   make test    — full test suite with coverage (fail < 80%)
#   make lint    — ruff check
#   make type    — mypy
#   make format  — ruff format
#   make gui     — launch the novice web GUI
#   make dry-youtube / dry-spotify — hooks-gate dry-runs against the real IPAs
#   make build-youtube / build-spotify — rebuild the hook dylibs

.PHONY: test lint type format check gui dry-youtube dry-spotify build-youtube build-spotify

YOUTUBE_IPA := /Users/nandan/dev/ytlite-ipa/com.google.ios.youtube_21.32.4_und3fined.ipa
SPOTIFY_IPA := /Users/nandan/Downloads/com.spotify.client_9.1.72_und3fined.ipa

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
	forge patch --ipa $(YOUTUBE_IPA) --patches patches/youtube/youtube.yaml --output /tmp/dry.ipa --dry-run

dry-spotify:
	forge patch --ipa $(SPOTIFY_IPA) --patches patches/spotify/spotify.yaml --output /tmp/dry.ipa --dry-run

build-youtube:
	patches/youtube/dylib/build.sh

build-spotify:
	patches/spotify/dylib/build.sh

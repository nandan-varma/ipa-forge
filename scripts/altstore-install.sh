#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Install an IPA on a paired iPhone through AltStore, hands-free.
#
#   scripts/altstore-install.sh <app.ipa> [--device NAME|UDID] [--timeout SECS]
#
# The Mac serves the IPA over HTTP, then devicectl launches AltStore on the
# phone with altstore://install?url=<ipa url>. AltStore downloads it and
# installs it through AltServer, exactly like picking the file by hand, so the
# app shows up in My Apps and refreshes normally. Feed it an unsigned build
# (`forge patch --no-sign`); AltStore signs at install time.
#
# Needs: Xcode (devicectl), the phone paired and on the same network, the
# phone unlocked, AltServer running on this Mac, AltStore on the phone.
set -euo pipefail

die() { echo "error: $1" >&2; exit 1; }
usage() { sed -n '4,6p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

ipa="" device="" timeout=600
while [[ $# -gt 0 ]]; do
  case "$1" in
    --device) device="${2:?}"; shift 2 ;;
    --timeout) timeout="${2:?}"; shift 2 ;;
    -h|--help) usage ;;
    -*) usage ;;
    *) [[ -z "$ipa" ]] || usage; ipa="$1"; shift ;;
  esac
done
[[ -n "$ipa" ]] || usage
[[ -f "$ipa" ]] || die "no such IPA: $ipa — build one with forge patch --no-sign"
ipa="$(cd "$(dirname "$ipa")" && pwd)/$(basename "$ipa")"

work="$(mktemp -d -t altstore-install)"
server_pid=""
cleanup() { [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null; rm -rf "$work"; }
trap cleanup EXIT

json() { python3 -I -c "$1" "${@:2}"; }

# --- device ---------------------------------------------------------------
xcrun devicectl list devices --json-output "$work/devices.json" >/dev/null 2>&1 \
  || die "devicectl failed — is Xcode installed?"
udid="$(json '
import json, sys
want = sys.argv[2].lower()
devs = [d for d in json.load(open(sys.argv[1]))["result"]["devices"]
        if d["connectionProperties"].get("transportType") != "sameMachine"]
def ok(d): return d["connectionProperties"].get("tunnelState") == "connected"
if want:
    devs = [d for d in devs if want in (d["deviceProperties"]["name"].lower().replace("’", "\x27"),
                                        d["hardwareProperties"].get("udid", "").lower())]
else:
    devs = [d for d in devs if ok(d) and d["hardwareProperties"].get("deviceType") == "iPhone"]
if devs and ok(devs[0]):
    print(devs[0]["hardwareProperties"]["udid"])
' "$work/devices.json" "${device//’/\'}")"
[[ -n "$udid" ]] || die "no connected device${device:+ matching \"$device\"} — unlock the phone, same Wi-Fi as this Mac, check Xcode > Devices"

# --- app info -------------------------------------------------------------
unzip -q -o "$ipa" 'Payload/*.app/Info.plist' -d "$work/ipa" || die "not an IPA: $ipa"
plist="$(ls "$work"/ipa/Payload/*.app/Info.plist | head -1)"
bundle_id="$(plutil -extract CFBundleIdentifier raw "$plist")"
version="$(plutil -extract CFBundleShortVersionString raw "$plist")"

apps() { xcrun devicectl device info apps --device "$udid" --json-output "$work/apps.json" >/dev/null 2>&1; }
# AltStore installs as <bundle id>.<TEAMID>; match the id itself or that form.
app_url() {
  json '
import json, sys
bid = sys.argv[2]
apps = json.load(open(sys.argv[1]))["result"]["apps"]
hits = sorted((a for a in apps if a["bundleIdentifier"] == bid or a["bundleIdentifier"].startswith(bid + ".")),
              key=lambda a: a["bundleIdentifier"] == bid)  # prefer the AltStore-suffixed id
if hits:
    print(hits[0].get("version", ""), hits[0]["url"])
' "$work/apps.json" "$bundle_id"
}

apps || die "could not list apps on the device — unlock it and retry"
altstore="$(json '
import json, sys
for a in json.load(open(sys.argv[1]))["result"]["apps"]:
    if a["bundleIdentifier"].endswith("com.rileytestut.AltStore"):
        print(a["bundleIdentifier"]); break
' "$work/apps.json")"
[[ -n "$altstore" ]] || die "AltStore is not installed on the device"
before="$(app_url)"

# --- serve ----------------------------------------------------------------
iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
ip="$(ipconfig getifaddr "${iface:-en0}" 2>/dev/null || true)"
[[ -n "$ip" ]] || die "no LAN address on ${iface:-en0} — is this Mac on Wi-Fi/Ethernet?"
pgrep -xq AltServer || die "AltServer is not running — open /Applications/AltServer.app"

mkdir -p "$work/www"
ln -s "$ipa" "$work/www/app.ipa"
port="$(json 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1])')"
python3 -I -m http.server "$port" --bind "$ip" --directory "$work/www" >"$work/http.log" 2>&1 &
server_pid=$!
sleep 1
kill -0 "$server_pid" 2>/dev/null || die "HTTP server failed: $(cat "$work/http.log")"

url="http://$ip:$port/app.ipa"
echo "installing $bundle_id $version via AltStore on $udid"
echo "  serving $url"

# --- trigger --------------------------------------------------------------
xcrun devicectl device process launch --device "$udid" --terminate-existing \
  --payload-url "altstore://install?url=$url" "$altstore" >"$work/launch.log" 2>&1 \
  || die "could not launch AltStore — is the phone unlocked? $(tail -3 "$work/launch.log")"

# --- wait -----------------------------------------------------------------
# Reinstalling moves the app to a new container, so a changed url means done.
deadline=$((SECONDS + timeout)) downloaded=""
while (( SECONDS < deadline )); do
  if [[ -z "$downloaded" ]] && grep -q 'GET /app.ipa HTTP[^"]*" 200' "$work/http.log"; then
    downloaded=1; echo "  AltStore downloaded the IPA; signing/installing via AltServer..."
  fi
  sleep 5
  apps || continue
  now="$(app_url)"
  if [[ -n "$now" && "$now" != "$before" ]]; then
    echo "installed: $bundle_id ${now%% *}"
    exit 0
  fi
done
[[ -n "$downloaded" ]] \
  && die "timed out after ${timeout}s — AltStore downloaded the IPA; check the phone for an AltStore error" \
  || die "timed out after ${timeout}s — AltStore never fetched $url (phone on another network? local-network access denied?)"

#!/bin/bash
# Build the Spotify tweak set from the EeveeSpotify source and stage the
# artifacts into build/ for the ipa-forge patch definition.
#
# Requires: theos with Swift support (THEOS), the EeveeSpotify source checkout.
#   THEOS=/Users/nandan/dev/ytlite-ipa/theos
#   EEVEE_SRC=/tmp/eevee3   (SideloadLabs/EeveeSpotifyReincarnated or any mirror)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export THEOS="${THEOS:-/Users/nandan/dev/ytlite-ipa/theos}"
export THEOS_PACKAGE_SCHEME=rootless
SRC="${EEVEE_SRC:-/tmp/eevee3}"
OUT="$HERE/build"
rm -rf "$OUT" && mkdir -p "$OUT"

[ -d "$SRC" ] || { echo "EeveeSpotify source not found at $SRC (set EEVEE_SRC)"; exit 1; }
[ -d "$THEOS" ] || { echo "theos not found at $THEOS (set THEOS)"; exit 1; }

echo "==> 1/3 EeveeSwiftProtobuf.framework"
bash "$SRC/Tools/SwiftProtobufBuild/build-eeveeswiftprotobuf.sh" >/dev/null
FW="$THEOS/lib/iphone/rootless/EeveeSwiftProtobuf.framework"
cp -R "$FW" "$OUT/EeveeSwiftProtobuf.framework"

echo "==> 2/3 EeveeSpotify package"
(cd "$SRC" && make package FINALPACKAGE=1 >/dev/null)
DEB="$(ls -t "$SRC"/packages/*.deb 2>/dev/null | head -1)"
[ -n "$DEB" ] || { echo "no EeveeSpotify .deb produced"; exit 1; }
mkdir -p /tmp/eevee_deb && rm -rf /tmp/eevee_deb/* && dpkg-deb -x "$DEB" /tmp/eevee_deb
DYLIB="$(find /tmp/eevee_deb -name 'EeveeSpotify.dylib' | head -1)"
BUNDLE="$(find /tmp/eevee_deb -name 'EeveeSpotify.bundle' -maxdepth 6 | head -1)"
[ -n "$DYLIB" ] && cp "$DYLIB" "$OUT/EeveeSpotify.dylib"
[ -n "$BUNDLE" ] && cp -R "$BUNDLE" "$OUT/EeveeSpotify.bundle"

echo "==> 3/3 zxPluginsInject"
(cd "$SRC/modules/zxPluginsInject" && make package FINALPACKAGE=1 >/dev/null)
ZDEB="$(ls -t "$SRC/modules/zxPluginsInject"/packages/*.deb 2>/dev/null | head -1)"
[ -n "$ZDEB" ] || { echo "no zxPluginsInject .deb produced"; exit 1; }
rm -rf /tmp/zx_deb && mkdir -p /tmp/zx_deb && dpkg-deb -x "$ZDEB" /tmp/zx_deb
ZSHIM="$(find /tmp/zx_deb -name 'zxPluginsInject.dylib' | head -1)"
[ -n "$ZSHIM" ] && cp "$ZSHIM" "$OUT/zxPluginsInject.dylib"

echo "staged: $(ls "$OUT")"

#!/usr/bin/env bash
set -euo pipefail

# Rebuilds fixtures/synthetic_app.ipa from fixtures/synthetic_app/src.
#
# The patch/sign pipeline only needs a stable, known-shape input; rebuilding
# via the iOS SDK on every test run would be slow and toolchain-version
# dependent, so the built .ipa is checked in and this script exists only for
# maintainers changing the fixture's shape.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC_DIR="$ROOT/fixtures/synthetic_app"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
ARCH=arm64
MIN_OS=13.0
CLANG=(xcrun --sdk iphoneos clang -arch "$ARCH" -miphoneos-version-min="$MIN_OS" -isysroot "$SDK")

APP_DIR="$BUILD_DIR/Payload/TestApp.app"
FW_DIR="$APP_DIR/Frameworks/TestFramework.framework"
mkdir -p "$FW_DIR" "$APP_DIR/Frameworks"

# 1. Embedded framework -- linked into TestApp, appears as a real LC_LOAD_DYLIB.
"${CLANG[@]}" -dynamiclib -install_name "@rpath/TestFramework.framework/TestFramework" \
    -o "$FW_DIR/TestFramework" "$SRC_DIR/src/framework_lib.c"
cp "$SRC_DIR/FrameworkInfo.plist" "$FW_DIR/Info.plist"

# 2. Standalone dylib -- never linked into TestApp; the clean Phase 4 injection target.
"${CLANG[@]}" -dynamiclib -install_name "@rpath/libInjectable.dylib" \
    -o "$APP_DIR/Frameworks/libInjectable.dylib" "$SRC_DIR/src/hook_lib.c"

# 3. Main executable, linked against the embedded framework.
"${CLANG[@]}" -F "$APP_DIR/Frameworks" -framework TestFramework \
    -Wl,-rpath,@executable_path/Frameworks \
    -o "$APP_DIR/TestApp" "$SRC_DIR/src/main.c"

cp "$SRC_DIR/AppInfo.plist" "$APP_DIR/Info.plist"
cp "$SRC_DIR/asset.txt" "$APP_DIR/asset.txt"

OUT="$ROOT/fixtures/synthetic_app.ipa"
rm -f "$OUT"
(cd "$BUILD_DIR" && zip -qq -r -y "$OUT" Payload)

echo "Built $OUT"

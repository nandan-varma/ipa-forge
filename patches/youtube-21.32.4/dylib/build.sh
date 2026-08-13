#!/bin/bash
# Builds libYTHook.dylib (arm64 iOS) from libYTHook.m and stages it at
# assets/libYTHook.dylib for the ipa-forge patch definition.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
xcrun --sdk iphoneos clang \
    -arch arm64 \
    -miphoneos-version-min=13.0 \
    -isysroot "$SDK" \
    -fobjc-arc \
    -dynamiclib \
    -install_name "@rpath/libYTHook.dylib" \
    -o "$HERE/../assets/libYTHook.dylib" \
    "$HERE/libYTHook.m"
echo "built $HERE/../assets/libYTHook.dylib"

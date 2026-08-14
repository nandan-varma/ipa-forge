#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
mkdir -p "$HERE/../build-test"
xcrun --sdk iphoneos clang \
    -arch arm64 -miphoneos-version-min=14.0 -isysroot "$SDK" \
    -fobjc-arc -dynamiclib -framework Foundation \
    -install_name "@rpath/MinimalHook.dylib" \
    -o "$HERE/../build-test/MinimalHook.dylib" "$HERE/MinimalHook.m"
echo "built $HERE/../build-test/MinimalHook.dylib"

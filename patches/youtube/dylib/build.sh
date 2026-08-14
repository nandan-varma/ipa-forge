#!/bin/bash
# Builds libYTHook.dylib (arm64 iOS) from all sources in this directory and
# stages it at assets/libYTHook.dylib for the ipa-forge patch definition.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
xcrun --sdk iphoneos clang \
    -arch arm64 \
    -miphoneos-version-min=14.0 \
    -isysroot "$SDK" \
    -fobjc-arc \
    -fobjc-weak \
    -dynamiclib \
    -framework Security \
    -framework UIKit \
    -framework UniformTypeIdentifiers \
    -framework MediaPlayer \
    -framework CoreGraphics \
    -framework AVFoundation \
    -install_name "@rpath/libYTHook.dylib" \
    -o "$HERE/../assets/libYTHook.dylib" \
    "$HERE"/*.m
echo "built $HERE/../assets/libYTHook.dylib"

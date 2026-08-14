#!/bin/bash
# Builds SpotifyHook.dylib (arm64 iOS) from all sources and stages it at
# ../build/SpotifyHook.dylib for the ipa-forge patch definition.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
mkdir -p "$HERE/../build"
xcrun --sdk iphoneos clang \
    -arch arm64 \
    -miphoneos-version-min=14.0 \
    -isysroot "$SDK" \
    -fobjc-arc \
    -fobjc-weak \
    -dynamiclib \
    -framework Foundation \
    -framework Security \
    -framework UIKit \
    -install_name "@rpath/SpotifyHook.dylib" \
    -o "$HERE/../build/SpotifyHook.dylib" \
    "$HERE"/SpotifyHook.m "$HERE"/SideloadFix.m "$HERE"/SessionProtection.m \
    "$HERE"/PremiumPatch.m "$HERE"/AdBlock.m "$HERE"/Settings.m "$HERE"/PBProto.m
echo "built $HERE/../build/SpotifyHook.dylib"

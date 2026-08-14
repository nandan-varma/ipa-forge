#!/bin/bash
# Builds IGModHook.dylib (arm64 iOS) from all sources and stages it at
# ../build/IGModHook.dylib for the ipa-forge patch definition.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
mkdir -p "$HERE/../build"
xcrun --sdk iphoneos clang \
	-arch arm64 \
	-miphoneos-version-min=15.0 \
	-isysroot "$SDK" \
	-fobjc-arc \
	-fobjc-weak \
	-dynamiclib \
	-framework Foundation \
	-framework UIKit \
	-framework Security \
	-install_name "@rpath/IGModHook.dylib" \
	-o "$HERE/../build/IGModHook.dylib" \
	"$HERE"/IGModHook.m "$HERE"/Helpers.m "$HERE"/AdBlock.m \
	"$HERE"/StoryPrivacy.m "$HERE"/MediaDownload.m "$HERE"/CopyText.m \
	"$HERE"/SafeMode.m "$HERE"/SettingsUI.m
echo "built $HERE/../build/IGModHook.dylib"

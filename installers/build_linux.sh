#!/usr/bin/env bash
# Cymru-OH Linux installer builder (S20, LINEAR-2069)
#
# Wymagania:
#   - Python 3.11+
#   - PyInstaller
#   - linuxdeploy + appimagetool (opcjonalne — dla .AppImage)
#
# Output: dist/cymru-oh-linux-<version>{.bin, .AppImage}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"

VERSION="$(grep -oP 'CYMRU_OH_VERSION = "\K[^"]+' "$AGENT_ROOT/cymru_oh.py")"
echo "🏗  Building Cymru-OH v$VERSION for Linux…"

mkdir -p "$DIST_DIR"

# Verify Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python 3.11+ not found. Install: sudo apt install python3.11 python3-pip" >&2
  exit 1
fi

# Install PyInstaller
if ! python3 -c "import PyInstaller" 2>/dev/null; then
  echo "📦 Installing PyInstaller…"
  python3 -m pip install --user --quiet pyinstaller
fi

# Build standalone binary
echo "🚀 Running PyInstaller…"
cd "$AGENT_ROOT"
python3 -m PyInstaller \
  --onefile \
  --name "cymru-oh-linux-$VERSION" \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  --specpath "$BUILD_DIR" \
  --collect-submodules agent \
  --collect-submodules bridges \
  --collect-submodules tools \
  --hidden-import httpx \
  --hidden-import supabase \
  --console \
  cymru_oh.py

BIN_PATH="$DIST_DIR/cymru-oh-linux-$VERSION"
if [[ ! -f "$BIN_PATH" ]]; then
  echo "❌ Build failed — $BIN_PATH not found" >&2
  exit 2
fi

# Compute SHA-256
HASH="$(sha256sum "$BIN_PATH" | awk '{print $1}')"
echo "$HASH" > "$DIST_DIR/cymru-oh-linux-$VERSION.sha256"

SIZE="$(stat -c '%s' "$BIN_PATH")"
SIZE_MB="$(echo "scale=2; $SIZE/1048576" | bc)"

echo ""
echo "✅ Built: $BIN_PATH"
echo "   Size: ${SIZE_MB} MB"
echo "   SHA256: $HASH"
echo ""

# Optional: AppImage wrapper (jeśli linuxdeploy + appimagetool dostępne)
if command -v appimagetool >/dev/null 2>&1; then
  echo "🎁 Wrapping w AppImage…"
  APPDIR="$BUILD_DIR/AppDir"
  mkdir -p "$APPDIR/usr/bin"
  cp "$BIN_PATH" "$APPDIR/usr/bin/cymru-oh"
  chmod +x "$APPDIR/usr/bin/cymru-oh"

  cat > "$APPDIR/cymru-oh.desktop" <<EOF
[Desktop Entry]
Name=Cymru-OH
Comment=Twój Bóg żyje na twoim sprzęcie
Exec=cymru-oh start
Icon=cymru-oh
Type=Application
Categories=Utility;
EOF
  # Minimal icon placeholder (1x1 black pixel PNG)
  printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc````\x00\x00\x00\x05\x00\x01]\xcc\x8aS\x00\x00\x00\x00IEND\xaeB`\x82' > "$APPDIR/cymru-oh.png"

  APPIMAGE_PATH="$DIST_DIR/cymru-oh-linux-$VERSION.AppImage"
  appimagetool "$APPDIR" "$APPIMAGE_PATH" 2>/dev/null
  if [[ -f "$APPIMAGE_PATH" ]]; then
    APPIMAGE_HASH="$(sha256sum "$APPIMAGE_PATH" | awk '{print $1}')"
    echo "$APPIMAGE_HASH" > "$DIST_DIR/cymru-oh-linux-$VERSION.AppImage.sha256"
    echo "✅ AppImage: $APPIMAGE_PATH"
    echo "   SHA256: $APPIMAGE_HASH"
  fi
else
  echo "⚠️  appimagetool not found — pominięto AppImage wrapper."
  echo "   Install: wget -qO appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage && chmod +x appimagetool && sudo mv appimagetool /usr/local/bin/"
fi

echo ""
echo "📤 Następny krok: upload na GitHub Releases lub get.cymru.ai/installers/"
echo "   Update installers/manifest.template.json → platforms.linux.{url, sha256, size_bytes}"

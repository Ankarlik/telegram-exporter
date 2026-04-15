#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Архитектура сборки. Если переменная не задана — берём архитектуру хоста,
# чтобы не пытаться собрать x86_64-бинарь на Apple Silicon раннере.
if [ -z "${TARGET_ARCH:-}" ]; then
  HOST_ARCH="$(uname -m)"
  case "$HOST_ARCH" in
    arm64|aarch64) export TARGET_ARCH="arm64" ;;
    *)             export TARGET_ARCH="x86_64" ;;
  esac
fi
echo "Building for TARGET_ARCH=$TARGET_ARCH"

# Если собираемся в x86_64 на Apple Silicon — нужно самопереподнять скрипт
# через Rosetta (/usr/bin/arch -x86_64), иначе universal2-Python будет
# выполняться как arm64 и pyinstaller соберёт arm64-бинарь.
HOST_ARCH="$(uname -m)"
if [ "$TARGET_ARCH" = "x86_64" ] && [ "$HOST_ARCH" = "arm64" ] && [ "${_BUILD_REEXEC:-0}" != "1" ]; then
  if [ ! -x /usr/bin/arch ]; then
    echo "Ошибка: нет /usr/bin/arch для перезапуска под Rosetta" >&2
    exit 1
  fi
  echo "Перезапуск под Rosetta (arch -x86_64)..."
  _BUILD_REEXEC=1 exec /usr/bin/arch -x86_64 /bin/bash "$0" "$@"
fi

# Выбор venv и python: для Intel-сборки используем universal2 python.org
# (он пришёл как pkg-установщик), запущенный под x86_64.
if [ "$TARGET_ARCH" = "x86_64" ]; then
  VENV_DIR="${VENV_DIR:-.venv_intel}"
  PYTHON_BIN="${PYTHON_BIN:-/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11}"
  if [ ! -x "$PYTHON_BIN" ]; then
    echo "Ошибка: не найден $PYTHON_BIN (нужен python.org universal2 3.11)" >&2
    exit 1
  fi
else
  VENV_DIR="${VENV_DIR:-.venv}"
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -c "import platform; print('venv Python arch:', platform.machine())"

pip install -r requirements.txt
pip install pyinstaller

ICON_PNG="${ICON_PNG:-$ROOT/assets/app_icon.png}"
ICON_DIR="$ROOT/icons"
ICON_ICNS="$ICON_DIR/app.icns"
ICON_ARG=""

if [ -f "$ICON_PNG" ]; then
  mkdir -p "$ICON_DIR"
  ICONSET="$ICON_DIR/app.iconset"
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  sips -z 16 16   "$ICON_PNG" --out "$ICONSET/icon_16x16.png" >/dev/null
  sips -z 32 32   "$ICON_PNG" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  sips -z 32 32   "$ICON_PNG" --out "$ICONSET/icon_32x32.png" >/dev/null
  sips -z 64 64   "$ICON_PNG" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$ICON_PNG" --out "$ICONSET/icon_128x128.png" >/dev/null
  sips -z 256 256 "$ICON_PNG" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$ICON_PNG" --out "$ICONSET/icon_256x256.png" >/dev/null
  sips -z 512 512 "$ICON_PNG" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$ICON_PNG" --out "$ICONSET/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$ICON_PNG" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET" -o "$ICON_ICNS"
  ICON_ARG="--icon \"$ICON_ICNS\""
fi

eval "pyinstaller --windowed --name \"Telegram Exporter\" $ICON_ARG \
  --target-arch \"$TARGET_ARCH\" \
  --exclude-module app_legacy \
  --exclude-module app \
  --collect-all customtkinter \
  --collect-all telethon \
  --collect-all faster_whisper \
  --collect-all ctranslate2 \
  --collect-all tokenizers \
  --collect-all imageio_ffmpeg \
  --collect-all tg_exporter \
  --hidden-import tg_exporter.ui.app \
  --hidden-import tg_exporter.core.orchestrator \
  --hidden-import tg_exporter.services.transcription.factory \
  --hidden-import keyring.backends \
  main.py"

APP_PATH="dist/Telegram Exporter.app"
DMG_NAME="${DMG_NAME:-TelegramExporter.dmg}"
DMG_PATH="dist/$DMG_NAME"

rm -f "$DMG_PATH"
hdiutil create -volname "Telegram Exporter" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"

echo "DMG готов: $DMG_PATH"

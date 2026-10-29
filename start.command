#!/bin/zsh
cd "${0:A:h}"
export PYTHONDONTWRITEBYTECODE=1
UV_BIN=$(command -v uv)
if [[ -z "$UV_BIN" && -x /opt/homebrew/bin/uv ]]; then
  UV_BIN=/opt/homebrew/bin/uv
fi
if [[ -z "$UV_BIN" ]]; then
  echo 'Не найден uv. Установите uv и повторите запуск.'
  exit 1
fi
SERVICE_TARGET="gui/$(id -u)/local.rgb2cmyk-cleaner"
if /bin/launchctl print "$SERVICE_TARGET" >/dev/null 2>&1; then
  echo 'Приложение работает как служба macOS: http://127.0.0.1:8765/'
  exit 0
fi
if [[ -f "$HOME/Library/LaunchAgents/local.rgb2cmyk-cleaner.plist" ]]; then
  exec "$UV_BIN" run --offline --no-sync --no-cache python -B service.py install
fi
echo 'Откройте http://127.0.0.1:8765 в браузере.'
exec "$UV_BIN" run uvicorn app:app --host 127.0.0.1 --port 8765

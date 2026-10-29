# Development

[Русский](development.md) · [English](development.en.md) · [简体中文](development.zh-CN.md)

Install Python dependencies with `uv sync --locked`. Running the app and integration tests requires a CMYK ICC profile at `profiles/source-fogra39.icc`; test expectations are based on FOGRA39.

## Checks

```sh
uv run python -B -m pytest -q -p no:cacheprovider
node --test tests/*.test.mjs
node --check frontend/workspace.js
```

Tests cover channel cleanup, ICC conversion, samplers, TIFF export, cancellation, session cleanup, translations, and language persistence. Test materials are created in isolated directories.

## Building the interface

After changing `frontend/`, rebuild `static/ui.js` and include it in your commit:

```sh
npm ci
npm run build
```

## Structure

- `app.py` — API and working-session management.
- `cleaner/` — color conversion, cleanup algorithm, and export.
- `frontend/` — interface source code.
- `frontend/locales.js` — Russian, English, and Chinese interface translations.
- `static/` — files served to the browser.
- `tests/` — Python and JavaScript tests.
- `service.py` — automatic startup management on macOS.

Uploads and exports are stored temporarily in `.runtime/`; previews are kept in memory. A new file, page reload, or server restart clears working data. The `.runtime/` and `profiles/` directories are excluded from Git.

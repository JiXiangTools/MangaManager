# MangaManager

> Windows-first, local-first manga library management with a FastAPI API, a React web UI, and an Electron desktop launcher.

**Languages:** English | [Simplified Chinese](docs/README.zh-CN.md) | [Japanese](docs/README.ja.md) | [Korean](docs/README.ko.md)

[![Star History Chart](https://api.star-history.com/svg?repos=JiXiangTools/MangaManager&type=Date)](https://www.star-history.com/#JiXiangTools/MangaManager&Date)

MangaManager is designed for users who want to manage, read, translate, and export a personal manga library from one machine. The Windows app starts the local web service automatically and can expose the web UI to other devices on the same network.

## Features

- Manage manga, chapters, covers, and page images.
- Import a whole folder as a manga from the Windows desktop client.
- Reorder chapters with drag-and-drop.
- Read chapters in strip mode or page mode.
- Switch reading language at any time; missing translations are shown as placeholders.
- Translate a manga, chapter, or image through the async proxy translation flow.
- Configure translation source language, target language, model, font, and concurrency.
- Export a whole manga or one chapter as a ZIP with `webp`, `jpg`, or `png` output.
- Use the same React UI for the browser and the Windows desktop shell.
- Require a temporary password for web access while allowing the trusted desktop client directly.
- Package a self-contained Windows build with embedded Python and PostgreSQL runtimes.

## Project Status

This project is under active development. The current app version is `1.0.1`.

The repository currently contains the application source, tests, and Windows packaging scripts. Before publishing as a public open-source project, review project governance documents if needed.

## Architecture

```text
MangaManager
|-- backend/   FastAPI, SQLAlchemy, Alembic, PostgreSQL-ready API
|-- frontend/  React + Vite + TypeScript shared UI
|-- windows/   Electron launcher and Windows packaging scripts
`-- shared/    Shared product metadata and catalog resources
```

Runtime data is stored under:

```text
data/
|-- library/   manga images, covers, and translated image files
|-- exports/   generated ZIP exports
`-- tmp/       temporary files
```

## Requirements

For the packaged Windows app:

- Windows build machine
- Node.js 18+
- Python runtime copied into `windows/runtime/python`
- PostgreSQL runtime copied into `windows/runtime/postgresql`

For local source development:

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+ for production-like development
- Docker, optional, for local PostgreSQL

## Quick Start

The primary usage path is to build a Windows ZIP and run MangaManager through the Windows app. The app starts the embedded PostgreSQL database and FastAPI backend service automatically.

Prepare the embedded runtime on a Windows build machine:

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

Build the Windows ZIP:

```bash
cd windows
npm install
npm run dist:win:zip
```

Extract the generated `windows/dist/MangaManager-<version>-win-x64.zip`, then run `MangaManager.exe`. On first launch, the app initializes PostgreSQL under `data/postgres` next to the portable app, starts the backend service, waits for `/api/health`, and loads the local web UI.

## Local Development

For source development without packaging, start PostgreSQL manually:

```bash
docker compose up -d postgres
```

Start the backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
export MANGAMANAGER_DATABASE_URL=postgresql+psycopg://mangamanager:mangamanager@localhost:55432/mangamanager
export MANGAMANAGER_TEMP_PASSWORD=devpass
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite dev server shown in the terminal. For direct backend hosting, build the frontend first and then open `http://127.0.0.1:8765`.

```bash
cd frontend
npm run build
```

## Windows Desktop Client

The Electron client is the normal runtime entrypoint for packaged use. It starts the embedded PostgreSQL process when needed, starts the local FastAPI service, waits for `/api/health`, and then loads the local web UI. In desktop mode, API requests include the desktop client header, so the Windows app does not require the web temporary password. Browser and LAN access still require the temporary password.

Run the desktop client in development:

```bash
cd windows
npm install
npm run dev
```

## Embedded Runtime

The packaged Windows app is intended to be self-contained. It expects this layout:

```text
windows/runtime/
  python/
    python.exe
    Lib/site-packages/...
  postgresql/
    bin/postgres.exe
    bin/initdb.exe
    bin/createdb.exe
```

Prepare the runtime on a Windows build machine before creating the ZIP:

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

The launcher initializes PostgreSQL on first launch under `data/postgres` next to the portable app and points the backend to:

```text
postgresql+psycopg://mangamanager@127.0.0.1:<postgresPort>/mangamanager
```

See [windows/runtime/README.md](windows/runtime/README.md) for details.

## Build a Windows ZIP

```bash
cd windows
npm install
npm run dist:win:zip
```

`npm run dist:win:zip` builds the frontend, verifies the embedded runtime, and creates a Windows ZIP package with Electron Builder. Distribute this ZIP to Windows users; they should extract it and launch `MangaManager.exe` instead of starting PostgreSQL or the backend manually.

## Translation

MangaManager uses the async proxy translation flow:

```text
POST /api/v1/translated/async
GET  /api/v1/translated/async/{plugin_id}
download translated_url
```

Manga and chapter translation split the scope into page images and process them with bounded concurrency. Translation requests include:

- `source_language`
- `target_language`
- `model_id`
- `font_style`
- `from=manager`
- `version=<MangaManager version>`

## Configuration

Backend settings use the `MANGAMANAGER_` environment prefix.

| Variable | Default | Description |
| --- | --- | --- |
| `MANGAMANAGER_DATABASE_URL` | `sqlite:///./data/mangamanager.db` | SQLAlchemy database URL. Use PostgreSQL for production-like usage. |
| `MANGAMANAGER_DATA_DIR` | `./data` | Library, export, and temporary file root. |
| `MANGAMANAGER_TEMP_PASSWORD` | empty | Web temporary password. |
| `MANGAMANAGER_TEMP_PASSWORD_HASH` | empty | Optional hashed web password. |
| `MANGAMANAGER_SESSION_SECRET` | `dev-session-secret` | Web session signing secret. |
| `MANGAMANAGER_DESKTOP_TOKEN` | empty | Local desktop access token used by the launcher. |
| `MANGAMANAGER_TRANSLATION_BASE_URL` | `https://www.mangatranslate.com` | Translation account API base URL. |
| `MANGAMANAGER_TRANSLATION_PROXY_BASE` | `https://plugin-server.mangatranslate.com` | Async proxy API base URL. |

## Tests

Run backend tests:

```bash
python -m pytest backend/tests/test_api.py backend/tests/test_translation_worker.py
```

Build the frontend:

```bash
cd windows
npm run build:frontend
```

## Security Notes

- The web UI is intended for trusted local or LAN use.
- Browser access requires the configured temporary password.
- The desktop client is trusted and bypasses the temporary password by design.
- Public HTTPS deployment, multi-user permissions, and remote hosting are out of scope for v1.

## Contributing

Issues and pull requests are welcome once the repository is published. Keep changes scoped, add tests for backend behavior, and run the frontend build before submitting UI changes.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

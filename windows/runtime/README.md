# Windows Embedded Runtime

The packaged Windows app expects these runtime folders:

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

`npm run dist:win:zip` runs `scripts/verify-runtime.js` before packaging, so a package cannot be produced unless Python and PostgreSQL are embedded.

Python must already include the backend dependencies from `backend/pyproject.toml` because the Electron launcher runs:

```text
runtime/python/python.exe -m uvicorn app.main:app
```

On a Windows build machine, prepare the runtime from existing local installations:

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

`PythonRoot` must contain `python.exe` and `pip`. `PostgresRoot` must contain `bin\postgres.exe`, `bin\initdb.exe`, and `bin\createdb.exe`. The script copies both runtimes and installs backend Python dependencies into `runtime/python/Lib/site-packages`.

PostgreSQL is initialized on first app launch into:

```text
<portable-app-folder>/data/postgres
```

The launcher starts bundled PostgreSQL on `127.0.0.1:<postgresPort>` and uses:

```text
postgresql+psycopg://mangamanager@127.0.0.1:<postgresPort>/mangamanager
```

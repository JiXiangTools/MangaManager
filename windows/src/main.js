const { app, BrowserWindow, ipcMain, Menu, dialog, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const http = require('http');
const net = require('net');
const crypto = require('crypto');
const { spawn, spawnSync } = require('child_process');
const { dataDir, loadConfig, saveConfig, hashPassword } = require('./config');

let mainWindow = null;
let backendProcess = null;
let postgresProcess = null;
const desktopToken = crypto.randomBytes(32).toString('hex');

function sendToMain(channel, ...args) {
  try {
    if (!mainWindow || mainWindow.isDestroyed() || !mainWindow.webContents || mainWindow.webContents.isDestroyed()) return;
    mainWindow.webContents.send(channel, ...args);
  } catch (_error) {
    // The app may be closing while child process streams are still flushing.
  }
}

function backendCwd() {
  return path.join(resourceRoot(), 'backend');
}

function resourceRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..', '..');
}

function frontendDist() {
  return path.join(resourceRoot(), 'frontend', 'dist');
}

function runtimeRoot() {
  return path.join(resourceRoot(), 'runtime');
}

function bundledPythonPath() {
  return path.join(runtimeRoot(), 'python', 'python.exe');
}

function postgresBinDir() {
  return path.join(runtimeRoot(), 'postgresql', 'bin');
}

function postgresExe(name) {
  return path.join(postgresBinDir(), `${name}.exe`);
}

function fileExists(target) {
  try {
    return fs.existsSync(target);
  } catch (_e) {
    return false;
  }
}

function pythonCommand() {
  const bundled = bundledPythonPath();
  if (process.platform === 'win32' && fileExists(bundled)) return bundled;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function backendUrl(cfg) {
  return `http://127.0.0.1:${cfg.webPort || 8765}`;
}

function bundledDatabaseUrl(cfg) {
  return `postgresql+psycopg://mangamanager@127.0.0.1:${cfg.postgresPort || 15432}/mangamanager`;
}

function backendEnv(cfg) {
  const shouldUseBundledPostgres = process.platform === 'win32' && cfg.useBundledPostgres !== false;
  const databaseUrl = shouldUseBundledPostgres ? bundledDatabaseUrl(cfg) : cfg.databaseUrl;
  const env = {
    ...process.env,
    MANGAMANAGER_DATABASE_URL: databaseUrl,
    MANGAMANAGER_DATA_DIR: dataDir(),
    MANGAMANAGER_FRONTEND_DIST: frontendDist(),
    MANGAMANAGER_TEMP_PASSWORD_HASH: cfg.webPassword ? hashPassword(cfg.webPassword) : '',
    MANGAMANAGER_SESSION_SECRET: 'electron-local-session',
    MANGAMANAGER_DESKTOP_TOKEN: desktopToken
  };
  if (cfg.webPassword) env.MANGAMANAGER_TEMP_PASSWORD = cfg.webPassword;
  return env;
}

function postgresDataDir() {
  return path.join(dataDir(), 'postgres');
}

function runPostgresTool(name, args, options = {}) {
  const exe = postgresExe(name);
  if (!fileExists(exe)) {
    throw new Error(`Bundled PostgreSQL tool missing: ${exe}`);
  }
  const result = spawnSync(exe, args, {
    cwd: postgresBinDir(),
    env: { ...process.env, ...options.env },
    encoding: 'utf8',
    windowsHide: true
  });
  if (result.status !== 0) {
    const stderr = String(result.stderr || result.stdout || '').trim();
    throw new Error(`${name} failed: ${stderr || `exit ${result.status}`}`);
  }
  return result;
}

function waitForTcp(host, port, attempts = 60) {
  return new Promise((resolve, reject) => {
    const check = (remaining) => {
      const socket = net.createConnection({ host, port }, () => {
        socket.end();
        resolve();
      });
      socket.on('error', () => retry(remaining));
      socket.setTimeout(1000, () => {
        socket.destroy();
        retry(remaining);
      });
    };
    const retry = (remaining) => {
      if (remaining <= 1) {
        reject(new Error(`PostgreSQL did not become ready at ${host}:${port}`));
        return;
      }
      setTimeout(() => check(remaining - 1), 500);
    };
    check(attempts);
  });
}

async function ensureBundledPostgres(cfg) {
  if (process.platform !== 'win32' || cfg.useBundledPostgres === false) return;
  const pgData = postgresDataDir();
  fs.mkdirSync(pgData, { recursive: true });

  if (!fileExists(path.join(pgData, 'PG_VERSION'))) {
    runPostgresTool('initdb', ['-D', pgData, '-U', 'mangamanager', '-A', 'trust', '--encoding=UTF8']);
  }

  if (!postgresProcess) {
    const postgres = postgresExe('postgres');
    if (!fileExists(postgres)) {
      throw new Error(`Bundled PostgreSQL server missing: ${postgres}`);
    }
    postgresProcess = spawn(postgres, ['-D', pgData, '-h', '127.0.0.1', '-p', String(cfg.postgresPort || 15432)], {
      cwd: postgresBinDir(),
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true
    });
    postgresProcess.stdout.on('data', (chunk) => sendToMain('backend:log', `[postgres] ${String(chunk)}`));
    postgresProcess.stderr.on('data', (chunk) => sendToMain('backend:log', `[postgres] ${String(chunk)}`));
    postgresProcess.on('exit', (code) => {
      sendToMain('backend:log', `[postgres] exited ${code}`);
      postgresProcess = null;
    });
  }

  await waitForTcp('127.0.0.1', Number(cfg.postgresPort || 15432));
  const createdb = postgresExe('createdb');
  if (fileExists(createdb)) {
    spawnSync(createdb, ['-h', '127.0.0.1', '-p', String(cfg.postgresPort || 15432), '-U', 'mangamanager', 'mangamanager'], {
      cwd: postgresBinDir(),
      env: process.env,
      encoding: 'utf8',
      windowsHide: true
    });
  }
}

async function startBackend() {
  const cfg = loadConfig();
  if (backendProcess) backendProcess.kill();
  await ensureBundledPostgres(cfg);
  backendProcess = spawn(
    pythonCommand(),
    ['-m', 'uvicorn', 'app.main:app', '--host', cfg.backendHost || '0.0.0.0', '--port', String(cfg.webPort || 8765)],
    {
      cwd: backendCwd(),
      env: backendEnv(cfg),
      stdio: ['ignore', 'pipe', 'pipe']
    }
  );
  backendProcess.stdout.on('data', (chunk) => {
    sendToMain('backend:log', String(chunk));
  });
  backendProcess.stderr.on('data', (chunk) => {
    sendToMain('backend:log', String(chunk));
  });
  backendProcess.on('exit', (code) => {
    sendToMain('backend:exit', code);
    backendProcess = null;
  });
}

function waitForBackend(url, attempts = 60) {
  return new Promise((resolve, reject) => {
    const check = (remaining) => {
      const req = http.get(`${url}/api/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
          return;
        }
        retry(remaining);
      });
      req.on('error', () => retry(remaining));
      req.setTimeout(1500, () => {
        req.destroy();
        retry(remaining);
      });
    };
    const retry = (remaining) => {
      if (remaining <= 1) {
        reject(new Error(`Backend did not become ready at ${url}`));
        return;
      }
      setTimeout(() => check(remaining - 1), 500);
    };
    check(attempts);
  });
}

async function loadFrontend(win) {
  const cfg = loadConfig();
  const localUrl = backendUrl(cfg);
  if (!app.isPackaged) {
    win.loadURL(cfg.frontendDevUrl).catch(() => {
      waitForBackend(localUrl)
        .then(() => win.loadURL(localUrl))
        .catch((error) => dialog.showErrorBox('MangaManager backend', error.message));
    });
    return;
  }
  try {
    await waitForBackend(localUrl);
    await win.loadURL(localUrl);
  } catch (error) {
    dialog.showErrorBox('MangaManager backend', error.message);
  }
}

function normalizeBaseUrl(baseUrl) {
  const value = String(baseUrl || '').trim().replace(/\/+$/, '');
  return value || 'https://www.mangatranslate.com';
}

async function cookieHeaderFromElectronSession(sess, baseUrl) {
  const url = `${normalizeBaseUrl(baseUrl)}/`;
  const cookies = await sess.cookies.get({ url }).catch(() => []);
  const parts = [];
  for (const cookie of cookies || []) {
    if (!cookie || !cookie.name) continue;
    parts.push(`${cookie.name}=${cookie.value || ''}`);
  }
  return parts.join('; ');
}

function openTranslationLoginWindow(baseUrl) {
  const startUrl = normalizeBaseUrl(baseUrl);
  return new Promise((resolve) => {
    const win = new BrowserWindow({
      width: 980,
      height: 760,
      title: 'MangaManager Translation Login',
      parent: mainWindow || undefined,
      modal: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        partition: 'persist:mangamanager-login'
      }
    });

    let settled = false;
    let allowClose = false;

    const finish = async (payload) => {
      if (settled) return;
      settled = true;
      allowClose = true;
      try {
        if (!win.isDestroyed()) win.close();
      } catch (_error) {
        // ignore
      }
      resolve(payload);
    };

    const capture = async () => {
      try {
        const rawCookie = await cookieHeaderFromElectronSession(win.webContents.session, startUrl);
        if (!rawCookie) {
          await finish({ ok: false, error: 'No auth cookies were captured.' });
          return;
        }
        await finish({ ok: true, raw_cookie: rawCookie });
      } catch (error) {
        await finish({ ok: false, error: String(error && (error.message || error.stack) || error) });
      }
    };

    win.on('close', (event) => {
      if (allowClose) return;
      event.preventDefault();
      capture().catch((error) => finish({ ok: false, error: String(error && (error.message || error.stack) || error) }));
    });

    win.loadURL(startUrl).catch((error) => {
      finish({ ok: false, error: String(error && (error.message || error.stack) || error) });
    });
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: 'MangaManager 1.0.0',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  loadFrontend(mainWindow);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function showSettingsWindow() {
  const cfg = loadConfig();
  const win = new BrowserWindow({
    width: 620,
    height: 460,
    title: 'MangaManager 1.0.0 Settings',
    parent: mainWindow || undefined,
    modal: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  const html = encodeURIComponent(`
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          body { font-family: system-ui, sans-serif; margin: 24px; color: #1d252c; }
          form { display: grid; gap: 12px; }
          label { display: grid; gap: 6px; }
          input { min-height: 34px; border: 1px solid #c8d3d6; border-radius: 6px; padding: 0 10px; }
          button { min-height: 36px; border: 0; border-radius: 6px; color: white; background: #2f5d62; }
          .hint { color: #5f6f76; font-size: 13px; }
        </style>
      </head>
      <body>
        <h1>MangaManager Settings</h1>
        <form id="form">
          <label>Web port <input name="webPort" type="number" min="1" max="65535" value="${cfg.webPort}" /></label>
          <label>Temporary password <input name="webPassword" type="password" value="${cfg.webPassword || ''}" /></label>
          <label><span><input name="useBundledPostgres" type="checkbox" ${cfg.useBundledPostgres !== false ? 'checked' : ''} /> Use bundled PostgreSQL</span></label>
          <label>Bundled PostgreSQL port <input name="postgresPort" type="number" min="1" max="65535" value="${cfg.postgresPort || 15432}" /></label>
          <label>PostgreSQL URL <input name="databaseUrl" value="${cfg.databaseUrl}" /></label>
          <label>Frontend dev URL <input name="frontendDevUrl" value="${cfg.frontendDevUrl}" /></label>
          <button>Save and restart backend</button>
          <div class="hint" id="status"></div>
        </form>
        <script>
          document.getElementById('form').addEventListener('submit', async (event) => {
            event.preventDefault();
            const data = Object.fromEntries(new FormData(event.currentTarget).entries());
            data.webPort = Number(data.webPort);
            data.postgresPort = Number(data.postgresPort);
            data.useBundledPostgres = data.useBundledPostgres === 'on';
            await window.mangaManager.saveConfig(data);
            await window.mangaManager.restartBackend();
            document.getElementById('status').textContent = 'Saved.';
          });
        </script>
      </body>
    </html>
  `);
  win.loadURL(`data:text/html;charset=utf-8,${html}`);
}

function setupMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {
      label: 'File',
      submenu: [
        { label: 'Settings', click: showSettingsWindow },
        { label: 'Open Web URL', click: () => shell.openExternal(backendUrl(loadConfig())) },
        { type: 'separator' },
        { role: 'quit' }
      ]
    },
    {
      label: 'View',
      submenu: [{ role: 'reload' }, { role: 'toggleDevTools' }]
    }
  ]));
}

ipcMain.handle('config:get', () => loadConfig());
ipcMain.handle('config:save', (_event, next) => saveConfig(next));
ipcMain.handle('backend:restart', async () => {
  await startBackend();
  return { ok: true };
});
ipcMain.handle('desktop:token', () => desktopToken);
ipcMain.handle('translation:open-login', async (_event, baseUrl) => openTranslationLoginWindow(baseUrl));
ipcMain.handle('manga:select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow || undefined, {
    title: 'Select manga folder',
    properties: ['openDirectory']
  });
  if (result.canceled || !result.filePaths || !result.filePaths[0]) {
    return { canceled: true };
  }
  return { canceled: false, path: result.filePaths[0] };
});
ipcMain.handle('dialog:error', (_event, message) => dialog.showErrorBox('MangaManager', String(message || 'Unknown error')));

app.whenReady().then(() => {
  setupMenu();
  startBackend().catch((error) => dialog.showErrorBox('MangaManager startup', String(error && error.message || error)));
  createWindow();
});

app.on('window-all-closed', () => {
  if (backendProcess) backendProcess.kill();
  if (postgresProcess) postgresProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill();
  if (postgresProcess) postgresProcess.kill();
});

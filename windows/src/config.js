const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function appRoot() {
  try {
    const { app } = require('electron');
    return app.isPackaged ? path.dirname(process.execPath) : path.resolve(__dirname, '..');
  } catch (_e) {
    return path.resolve(__dirname, '..');
  }
}

function dataDir() {
  return path.join(appRoot(), 'data');
}

function configPath() {
  return path.join(dataDir(), 'config.json');
}

const DEFAULT_CONFIG = {
  webPort: 8765,
  webPassword: '',
  useBundledPostgres: true,
  postgresPort: 15432,
  databaseUrl: 'postgresql+psycopg://mangamanager@127.0.0.1:15432/mangamanager',
  backendHost: '0.0.0.0',
  frontendDevUrl: 'http://127.0.0.1:5173'
};

function ensureDataDir() {
  fs.mkdirSync(dataDir(), { recursive: true });
}

function loadConfig() {
  ensureDataDir();
  if (!fs.existsSync(configPath())) return { ...DEFAULT_CONFIG };
  try {
    return { ...DEFAULT_CONFIG, ...JSON.parse(fs.readFileSync(configPath(), 'utf8')) };
  } catch (_e) {
    return { ...DEFAULT_CONFIG };
  }
}

function saveConfig(next) {
  ensureDataDir();
  const merged = { ...loadConfig(), ...(next || {}) };
  fs.writeFileSync(configPath(), JSON.stringify(merged, null, 2), 'utf8');
  return merged;
}

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const digest = crypto.pbkdf2Sync(String(password || ''), salt, 120000, 32, 'sha256').toString('hex');
  return `pbkdf2_sha256$${salt}$${digest}`;
}

module.exports = {
  appRoot,
  dataDir,
  loadConfig,
  saveConfig,
  hashPassword
};

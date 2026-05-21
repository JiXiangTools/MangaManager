const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('mangaManager', {
  isDesktop: true,
  getConfig: () => ipcRenderer.invoke('config:get'),
  saveConfig: (payload) => ipcRenderer.invoke('config:save', payload),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  onBackendLog: (handler) => {
    ipcRenderer.on('backend:log', (_event, message) => handler(message));
  },
  onBackendExit: (handler) => {
    ipcRenderer.on('backend:exit', (_event, code) => handler(code));
  },
  openTranslationLogin: (baseUrl) => ipcRenderer.invoke('translation:open-login', baseUrl),
  selectMangaFolder: () => ipcRenderer.invoke('manga:select-folder')
});

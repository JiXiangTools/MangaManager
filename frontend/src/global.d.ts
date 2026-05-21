type MangaManagerBridge = {
  isDesktop?: boolean;
  getConfig?: () => Promise<unknown>;
  saveConfig?: (payload: unknown) => Promise<unknown>;
  restartBackend?: () => Promise<unknown>;
  onBackendLog?: (handler: (message: string) => void) => void;
  onBackendExit?: (handler: (code: number) => void) => void;
  openTranslationLogin?: (baseUrl: string) => Promise<unknown>;
  selectMangaFolder?: () => Promise<unknown>;
};

declare global {
  interface Window {
    mangaManager?: MangaManagerBridge;
  }
}

export {};

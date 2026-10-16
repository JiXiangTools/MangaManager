import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BookOpen, ChevronLeft, ChevronRight, Download, ExternalLink, FolderOpen, FolderPlus, GripVertical, Languages, Library, Maximize2, Minimize2, Pencil, Play, Settings, Tags, Trash2, Upload } from 'lucide-react';
import { api, Catalogs, Chapter, Manga, ReadResponse, TranslatePayload, TranslationCredentials, isDesktopRuntime } from './api';
import { formatT, langDir, t, UiLang, uiLanguages } from './i18n';
import product from '../../shared/product.json';
import './styles.css';

const APP_VERSION = product.version || '1.0.0';
const DEFAULT_LANGUAGE = 'en';
const MIN_TRANSLATION_CONCURRENCY = 1;
const MAX_TRANSLATION_CONCURRENCY = 16;

type Mode = 'strip' | 'page';
type View = 'settings' | 'manga' | 'reader';
type Notice = {
  title: string;
  body?: string;
  href?: string;
  hrefLabel?: string;
};

type ReaderProgress = {
  pageIndex: number;
  scrollRatio: number;
};

type ImportedFile = {
  file: File;
  parts: string[];
  relativePath: string;
};

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff', 'avif']);
const MAX_FOLDER_IMPORT_IMAGES = 5000;

function clampTranslationConcurrency(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 3;
  return Math.max(MIN_TRANSLATION_CONCURRENCY, Math.min(MAX_TRANSLATION_CONCURRENCY, Math.trunc(parsed)));
}

function isVisibleImageFile(file: File, parts: string[]): boolean {
  if (parts.some((part) => part.startsWith('.'))) return false;
  const extension = file.name.split('.').pop()?.toLowerCase() || '';
  return IMAGE_EXTENSIONS.has(extension);
}

function extractSortNumber(value: string): number | null {
  const match = value.match(/\d+(?:\.\d+)?/);
  if (!match) return null;
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function chapterNameSort(a: string, b: string): number {
  const left = extractSortNumber(a);
  const right = extractSortNumber(b);
  if (left !== null && right !== null && left !== right) return left - right;
  if (left !== null && right === null) return -1;
  if (left === null && right !== null) return 1;
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

function fileNameSort(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

function csvValues(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function uniqueCsv(value: string): string {
  return Array.from(new Set(csvValues(value))).join(', ');
}

function languageLabel(code: string, locale: string): string {
  try {
    const displayNames = new Intl.DisplayNames([locale], { type: 'language' });
    return displayNames.of(code) || code;
  } catch (_error) {
    return code;
  }
}

function languageOptionLabel(code: string, uiLang: UiLang): string {
  const currentLabel = languageLabel(code, uiLang);
  const nativeLabel = languageLabel(code, code);
  return `${currentLabel} (${nativeLabel})`;
}

function resolveInitialUiLanguage(): UiLang {
  const stored = localStorage.getItem('uiLang') as UiLang | null;
  const migrated = localStorage.getItem('defaultLanguageMigratedToEnglish');
  if (stored === 'zh-CN' && migrated !== '1') {
    localStorage.setItem('uiLang', DEFAULT_LANGUAGE);
    localStorage.setItem('defaultLanguageMigratedToEnglish', '1');
    return DEFAULT_LANGUAGE;
  }
  if (!migrated) {
    localStorage.setItem('defaultLanguageMigratedToEnglish', '1');
  }
  return stored || DEFAULT_LANGUAGE;
}

function App() {
  const [uiLang, setUiLang] = useState<UiLang>(resolveInitialUiLanguage);
  const [unlocked, setUnlocked] = useState(() => isDesktopRuntime());
  const [activeView, setActiveView] = useState<View>('manga');
  const [password, setPassword] = useState('');
  const [manga, setManga] = useState<Manga[]>([]);
  const [selectedManga, setSelectedManga] = useState<Manga | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null);
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null);
  const [read, setRead] = useState<ReadResponse | null>(null);
  const [mode, setMode] = useState<Mode>('strip');
  const [readLang, setReadLang] = useState(DEFAULT_LANGUAGE);
  const [sourceLang, setSourceLang] = useState(DEFAULT_LANGUAGE);
  const [targetLang, setTargetLang] = useState(DEFAULT_LANGUAGE);
  const [modelId, setModelId] = useState('CTD');
  const [fontId, setFontId] = useState('auto');
  const [format, setFormat] = useState('webp');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [pendingAction, setPendingAction] = useState('');
  const [translationEmail, setTranslationEmail] = useState('');
  const [translationPassword, setTranslationPassword] = useState('');
  const [translationBaseUrl, setTranslationBaseUrl] = useState(localStorage.getItem('translationBaseUrl') || 'https://www.mangatranslate.com');
  const [translationConcurrency, setTranslationConcurrency] = useState(() => clampTranslationConcurrency(localStorage.getItem('translationConcurrency') || 3));
  const [translationCreds, setTranslationCreds] = useState<TranslationCredentials | null>(() => {
    const raw = localStorage.getItem('translationCredentials');
    if (!raw) return null;
    try {
      return JSON.parse(raw) as TranslationCredentials;
    } catch (_error) {
      return null;
    }
  });
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [createLanguage, setCreateLanguage] = useState<string>((localStorage.getItem('uiLang') as UiLang) || DEFAULT_LANGUAGE);
  const [createCategory, setCreateCategory] = useState('');
  const [createTags, setCreateTags] = useState('');
  const [categoryOptions, setCategoryOptions] = useState(() => localStorage.getItem('mangaCategoryOptions') || '');
  const [tagOptions, setTagOptions] = useState(() => localStorage.getItem('mangaTagOptions') || '');
  const [mangaSearch, setMangaSearch] = useState('');
  const [mangaCategoryFilter, setMangaCategoryFilter] = useState('');
  const [mangaTagFilter, setMangaTagFilter] = useState('');
  const [selectedMangaIds, setSelectedMangaIds] = useState<Set<string>>(() => new Set());
  const [bulkCategory, setBulkCategory] = useState('');
  const [bulkTags, setBulkTags] = useState('');
  const [draggedChapterId, setDraggedChapterId] = useState('');
  const [fullscreenReader, setFullscreenReader] = useState(false);
  const [failedImageIds, setFailedImageIds] = useState<Set<string>>(() => new Set());
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [readerChromeVisible, setReaderChromeVisible] = useState(false);
  const readerRef = useRef<HTMLElement | null>(null);
  const chaptersRef = useRef<Chapter[]>([]);
  const dragFinishedRef = useRef(false);
  const readerChromeTimerRef = useRef<number | null>(null);
  const pendingReaderRestoreRef = useRef<ReaderProgress | null>(null);
  const translationEventSignaturesRef = useRef<Record<string, string>>({});

  const dir = langDir(uiLang);
  const labels = useMemo(() => ({ t: (key: string) => t(uiLang, key) }), [uiLang]);
  const selectedChapterIndex = selectedChapter ? chapters.findIndex((chapter) => chapter.id === selectedChapter.id) : -1;
  const previousChapter = (read?.previous_chapter_id && chapters.find((chapter) => chapter.id === read.previous_chapter_id))
    || (selectedChapterIndex > 0 ? chapters[selectedChapterIndex - 1] : null);
  const nextChapter = (read?.next_chapter_id && chapters.find((chapter) => chapter.id === read.next_chapter_id))
    || (selectedChapterIndex >= 0 && selectedChapterIndex < chapters.length - 1 ? chapters[selectedChapterIndex + 1] : null);
  const translatedPages = read?.pages.filter((page) => !page.missing).length || 0;
  const missingPages = read?.pages.filter((page) => page.missing).length || 0;
  const readerPages = read ? (mode === 'page' ? read.pages.slice(currentPageIndex, currentPageIndex + 1) : read.pages) : [];
  const canGoPreviousPage = mode === 'page' && currentPageIndex > 0;
  const canGoNextPage = mode === 'page' && Boolean(read && currentPageIndex < read.pages.length - 1);
  const translationConnected = Boolean(translationCreds?.user_id && (translationCreds?.access_token || translationCreds?.raw_cookie || translationCreds?.email));
  const defaultReadLanguage = selectedManga?.default_language?.trim() || readLang;
  const mangaLanguageOptions = useMemo(() => {
    const values = new Set<string>();
    for (const lang of [
      ...(catalogs?.sourceLanguages || []),
      ...uiLanguages.map((item) => item.code)
    ]) {
      const value = String(lang || '').trim();
      if (value) values.add(value);
    }
    return Array.from(values);
  }, [catalogs]);
  const readLanguageOptions = useMemo(() => {
    const values = new Set<string>();
    for (const lang of [
      ...(catalogs?.sourceLanguages || []),
      ...(catalogs?.targetLanguages || []),
      selectedManga?.default_language,
      readLang
    ]) {
      const value = String(lang || '').trim();
      if (value) values.add(value);
    }
    return Array.from(values);
  }, [catalogs, readLang, selectedManga?.default_language]);
  const categoryList = useMemo(() => {
    const values = new Set([...csvValues(categoryOptions), ...manga.map((item) => item.category).filter(Boolean)]);
    return Array.from(values).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
  }, [categoryOptions, manga]);
  const tagList = useMemo(() => {
    const values = new Set([...csvValues(tagOptions), ...manga.flatMap((item) => csvValues(item.tags || ''))]);
    return Array.from(values).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
  }, [tagOptions, manga]);
  const filteredManga = useMemo(() => {
    const query = mangaSearch.trim().toLowerCase();
    return manga.filter((item) => {
      const itemTags = csvValues(item.tags || '');
      const matchesName = !query || item.name.toLowerCase().includes(query);
      const matchesCategory = !mangaCategoryFilter || item.category === mangaCategoryFilter;
      const matchesTag = !mangaTagFilter || itemTags.includes(mangaTagFilter);
      return matchesName && matchesCategory && matchesTag;
    });
  }, [manga, mangaCategoryFilter, mangaSearch, mangaTagFilter]);

  function addLog(message: string) {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((current) => [...current, `[ui ${timestamp}] ${message}`].slice(-200));
  }

  function progressKey(chapterId: string, lang: string, readerMode: Mode): string {
    return `readerProgress:${chapterId}:${lang}:${readerMode}`;
  }

  function loadReaderProgress(chapterId: string, lang: string, readerMode: Mode): ReaderProgress {
    const raw = localStorage.getItem(progressKey(chapterId, lang, readerMode));
    if (!raw) return { pageIndex: 0, scrollRatio: 0 };
    try {
      const parsed = JSON.parse(raw) as Partial<ReaderProgress>;
      return {
        pageIndex: Math.max(0, Math.trunc(Number(parsed.pageIndex || 0))),
        scrollRatio: Math.max(0, Math.min(1, Number(parsed.scrollRatio || 0)))
      };
    } catch (_error) {
      return { pageIndex: 0, scrollRatio: 0 };
    }
  }

  function saveReaderProgress(chapterId = selectedChapter?.id, lang = readLang, readerMode = mode) {
    if (!chapterId) return;
    const reader = readerRef.current;
    const maxScroll = reader ? Math.max(1, reader.scrollHeight - reader.clientHeight) : 1;
    const scrollRatio = readerMode === 'strip' && reader ? Math.max(0, Math.min(1, reader.scrollTop / maxScroll)) : 0;
    const progress: ReaderProgress = {
      pageIndex: readerMode === 'page' ? currentPageIndex : 0,
      scrollRatio
    };
    localStorage.setItem(progressKey(chapterId, lang, readerMode), JSON.stringify(progress));
  }

  function switchView(view: View) {
    saveReaderProgress();
    setActiveView(view);
  }

  function showReaderChrome() {
    setReaderChromeVisible(true);
    if (readerChromeTimerRef.current) {
      window.clearTimeout(readerChromeTimerRef.current);
    }
    readerChromeTimerRef.current = window.setTimeout(() => {
      setReaderChromeVisible(false);
      readerChromeTimerRef.current = null;
    }, 2000);
  }

  function handleReaderMouseMove(event: React.MouseEvent<HTMLElement>) {
    const reader = readerRef.current;
    if (!reader) return;
    const top = reader.getBoundingClientRect().top;
    if (event.clientY - top <= 96) {
      showReaderChrome();
    }
  }

  useEffect(() => {
    localStorage.setItem('uiLang', uiLang);
    document.documentElement.lang = uiLang;
    document.documentElement.dir = dir;
    if (mangaLanguageOptions.includes(uiLang)) {
      setCreateLanguage(uiLang);
    }
  }, [uiLang, dir, mangaLanguageOptions]);

  useEffect(() => {
    localStorage.setItem('translationConcurrency', String(translationConcurrency));
  }, [translationConcurrency]);

  useEffect(() => {
    localStorage.setItem('mangaCategoryOptions', uniqueCsv(categoryOptions));
  }, [categoryOptions]);

  useEffect(() => {
    localStorage.setItem('mangaTagOptions', uniqueCsv(tagOptions));
  }, [tagOptions]);

  useEffect(() => {
    const bridge = window.mangaManager;
    if (!bridge?.onBackendLog) return;
    bridge.onBackendLog((message) => {
      setLogs((current) => {
        const next = [...current, String(message || '').trim()].filter(Boolean);
        return next.slice(-200);
      });
    });
    bridge.onBackendExit?.((code) => {
      setLogs((current) => [...current.slice(-199), `[backend] exited ${code}`]);
    });
  }, []);

  useEffect(() => {
    if (unlocked) {
      void bootstrap();
    }
  }, [unlocked]);

  useEffect(() => {
    chaptersRef.current = chapters;
  }, [chapters]);

  useEffect(() => {
    const onFullscreenChange = () => {
      saveReaderProgress();
      setFullscreenReader(document.fullscreenElement === readerRef.current);
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  useEffect(() => {
    return () => {
      if (readerChromeTimerRef.current) {
        window.clearTimeout(readerChromeTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    setCurrentPageIndex((index) => {
      const pageCount = read?.pages.length || 0;
      if (!pageCount) return 0;
      return Math.min(index, pageCount - 1);
    });
  }, [read]);

  useEffect(() => {
    if (mode === 'page' && read?.chapter_id) {
      saveReaderProgress(read.chapter_id, readLang, mode);
    }
  }, [currentPageIndex, mode, read?.chapter_id, readLang]);

  useEffect(() => {
    const progress = pendingReaderRestoreRef.current;
    if (!read || !progress) return;
    pendingReaderRestoreRef.current = null;
    if (mode === 'page') {
      setCurrentPageIndex(Math.min(progress.pageIndex, Math.max(0, read.pages.length - 1)));
      return;
    }
    window.requestAnimationFrame(() => {
      const reader = readerRef.current;
      if (!reader) return;
      const maxScroll = Math.max(0, reader.scrollHeight - reader.clientHeight);
      reader.scrollTop = maxScroll * progress.scrollRatio;
    });
  }, [read, mode]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (mode !== 'page' || !read) return;
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(target.tagName)) return;
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        setCurrentPageIndex((index) => Math.max(0, index - 1));
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        setCurrentPageIndex((index) => Math.min(read.pages.length - 1, index + 1));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mode, read]);

  async function bootstrap() {
    const [nextCatalogs, nextManga] = await Promise.all([api.catalogs(), api.listManga()]);
    setCatalogs(nextCatalogs);
    setManga(nextManga);
    if (!selectedManga && nextManga[0]) {
      setSelectedManga(nextManga[0]);
      const nextChapters = await api.listChapters(nextManga[0].id);
      setChapters(nextChapters);
      setSelectedChapter(nextChapters[0] || null);
      setReadLang(nextManga[0].default_language || nextCatalogs.targetLanguages[0] || DEFAULT_LANGUAGE);
    }
    setSourceLang(nextCatalogs.sourceLanguages.includes(DEFAULT_LANGUAGE) ? DEFAULT_LANGUAGE : nextCatalogs.sourceLanguages[0] || DEFAULT_LANGUAGE);
    setTargetLang(nextCatalogs.targetLanguages.includes(DEFAULT_LANGUAGE) ? DEFAULT_LANGUAGE : nextCatalogs.targetLanguages[0] || DEFAULT_LANGUAGE);
    setModelId(nextCatalogs.models.defaultModel);
    setFontId(nextCatalogs.fonts.defaultStyle);
  }

  async function unlock(event: React.FormEvent) {
    event.preventDefault();
    await api.login(password);
    setUnlocked(true);
  }

  async function connectTranslation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPendingAction('translation-login');
    setNotice({ title: labels.t('working') });
    try {
      const creds = await api.translationLogin({
        email: translationEmail,
        password: translationPassword,
        base_url: translationBaseUrl
      });
      const nextCreds = { ...creds, email: creds.email || translationEmail, base_url: translationBaseUrl };
      localStorage.setItem('translationCredentials', JSON.stringify(nextCreds));
      localStorage.setItem('translationBaseUrl', translationBaseUrl);
      setTranslationCreds(nextCreds);
      setTranslationPassword('');
      setNotice({ title: labels.t('translationConnected'), body: formatT(uiLang, 'taskId', { id: creds.user_id }) });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function connectBrowserTranslation() {
    setPendingAction('translation-browser-login');
    setNotice({ title: labels.t('working') });
    try {
      const bridge = window.mangaManager;
      if (!bridge?.openTranslationLogin) {
        throw new Error('Browser login is not available in this runtime.');
      }
      const opened = await bridge.openTranslationLogin(translationBaseUrl);
      const loginResult = opened as { ok?: boolean; error?: string; raw_cookie?: string; rawCookie?: string; user_id?: string; userId?: string; email?: string; access_token?: string; accessToken?: string } | null;
      if (loginResult && loginResult.ok === false) {
        throw new Error(String(loginResult.error || 'Browser login failed.'));
      }
      const rawCookie = String(loginResult?.raw_cookie || loginResult?.rawCookie || '').trim();
      if (!rawCookie) {
        throw new Error('No login cookie was captured.');
      }
      const creds = await api.translationCookieLogin({
        raw_cookie: rawCookie,
        base_url: translationBaseUrl,
        user_id: String(loginResult?.user_id || loginResult?.userId || '').trim(),
        email: String(loginResult?.email || '').trim(),
        access_token: String(loginResult?.access_token || loginResult?.accessToken || '').trim()
      });
      const nextCreds = { ...creds, base_url: translationBaseUrl };
      localStorage.setItem('translationCredentials', JSON.stringify(nextCreds));
      localStorage.setItem('translationBaseUrl', translationBaseUrl);
      setTranslationCreds(nextCreds);
      setNotice({ title: labels.t('translationConnected'), body: formatT(uiLang, 'taskId', { id: creds.user_id }) });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function importMangaFolder(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = '';
    if (!files.length) return;
    setPendingAction('import-folder');
    setNotice({ title: labels.t('working') });
    try {
      const normalized = files
        .map((file) => {
          const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
          const parts = relativePath.split('/').filter(Boolean);
          return { file, parts, relativePath };
        })
        .filter(({ file, parts }) => parts.length >= 2 && isVisibleImageFile(file, parts));

      if (!normalized.length) {
        throw new Error('Selected folder does not contain chapter subfolders.');
      }
      if (normalized.length > MAX_FOLDER_IMPORT_IMAGES) {
        throw new Error(`Selected folder contains ${normalized.length} images. Maximum is ${MAX_FOLDER_IMPORT_IMAGES}.`);
      }

      const mangaName = normalized[0].parts[0];
      const chapterMap = new Map<string, { title: string; files: ImportedFile[] }>();
      for (const item of normalized) {
        const chapterName = item.parts[1] || mangaName;
        const key = `${item.parts[0]}::${chapterName}`;
        if (!chapterMap.has(key)) {
          chapterMap.set(key, { title: chapterName, files: [] });
        }
        chapterMap.get(key)!.files.push(item);
      }

      const created = await api.createManga({
        name: mangaName,
        homepage: '',
        default_language: createLanguage || DEFAULT_LANGUAGE,
        category: createCategory,
        tags: uniqueCsv(createTags)
      });

      let chapterIndex = 0;
      const chapterGroups = Array.from(chapterMap.values()).sort((a, b) => chapterNameSort(a.title, b.title));
      for (const group of chapterGroups) {
        chapterIndex += 1;
        const chapter = await api.createChapter(created.id, {
          title: group.title,
          number: String(chapterIndex),
          sort_order: chapterIndex
        });
        const orderedFiles = group.files
          .slice()
          .sort((a, b) => fileNameSort(a.relativePath, b.relativePath))
          .map((item) => item.file);
        await api.uploadImages(chapter.id, orderedFiles);
      }

      const firstImage = chapterGroups[0]?.files?.slice().sort((a, b) => fileNameSort(a.relativePath, b.relativePath))[0]?.file || null;
      if (firstImage) {
        await api.uploadMangaCover(created.id, firstImage);
      }

      const nextManga = await api.listManga();
      setManga(nextManga);
      const selected = nextManga.find((item) => item.id === created.id) || created;
      setSelectedManga(selected);
      const nextChapters = await api.listChapters(created.id);
      setChapters(nextChapters);
      setSelectedChapter(nextChapters[0] || null);
      setRead(null);
      setReadLang(selected.default_language || DEFAULT_LANGUAGE);
      setNotice({ title: labels.t('createManga'), body: selected.name });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function importMangaFolderFromDesktop() {
    setPendingAction('import-folder');
    setNotice({ title: labels.t('working') });
    try {
      const bridge = window.mangaManager;
      if (!bridge?.selectMangaFolder) {
        throw new Error('Folder import is not available in this runtime.');
      }
      const selected = await bridge.selectMangaFolder() as { canceled?: boolean; path?: string } | null;
      if (!selected || selected.canceled) {
        setNotice(null);
        return;
      }
      if (!selected.path) {
        throw new Error('No folder was selected.');
      }
      const created = await api.importFolder({
        folder_path: selected.path,
        default_language: createLanguage || DEFAULT_LANGUAGE,
        max_images: MAX_FOLDER_IMPORT_IMAGES
      });
      const categorized = await api.updateManga(created.id, {
        category: createCategory,
        tags: uniqueCsv(createTags)
      });
      const nextManga = await api.listManga();
      setManga(nextManga);
      const nextSelected = nextManga.find((item) => item.id === categorized.id) || categorized;
      setSelectedManga(nextSelected);
      const nextChapters = await api.listChapters(created.id);
      setChapters(nextChapters);
      setSelectedChapter(nextChapters[0] || null);
      setRead(null);
      setReadLang(nextSelected.default_language || DEFAULT_LANGUAGE);
      setCreateCategory('');
      setCreateTags('');
      setNotice({ title: labels.t('createManga'), body: nextSelected.name });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function createManga(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPendingAction('create-manga');
    setNotice({ title: labels.t('working') });
    const data = new FormData(event.currentTarget);
    try {
      const payload = {
        name: String(data.get('name') || ''),
        homepage: '',
        default_language: String(data.get('default_language') || DEFAULT_LANGUAGE),
        category: String(data.get('category') || ''),
        tags: uniqueCsv(String(data.get('tags') || '')),
        coverImage: coverFile
      };
      const created = coverFile
        ? await api.createMangaWithCover(payload)
        : await api.createManga(payload);
      setManga(await api.listManga());
      setSelectedManga(created);
      setChapters([]);
      setSelectedChapter(null);
      setRead(null);
      setReadLang(created.default_language || DEFAULT_LANGUAGE);
      setCoverFile(null);
      setCreateCategory('');
      setCreateTags('');
      event.currentTarget.reset();
      setNotice({ title: labels.t('createManga'), body: created.name });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function loadChapters(item: Manga) {
    saveReaderProgress();
    setSelectedManga(item);
    const next = await api.listChapters(item.id);
    setChapters(next);
    setSelectedChapter(next[0] || null);
    setRead(null);
    setReadLang(item.default_language || DEFAULT_LANGUAGE);
  }

  async function deleteManga(item: Manga) {
    if (!window.confirm(formatT(uiLang, 'confirmDeleteManga', { name: item.name }))) return;
    setPendingAction(`delete-manga-${item.id}`);
    try {
      await api.deleteManga(item.id);
      const nextManga = await api.listManga();
      setManga(nextManga);
      if (selectedManga?.id === item.id) {
        const nextSelected = nextManga[0] || null;
        setSelectedManga(nextSelected);
        if (nextSelected) {
          const nextChapters = await api.listChapters(nextSelected.id);
          setChapters(nextChapters);
          setSelectedChapter(nextChapters[0] || null);
          setReadLang(nextSelected.default_language || DEFAULT_LANGUAGE);
        } else {
          setChapters([]);
          setSelectedChapter(null);
          setReadLang(DEFAULT_LANGUAGE);
        }
        setRead(null);
      }
      setNotice({ title: labels.t('deleteManga'), body: item.name });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function updateSelectedManga(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedManga) return;
    setPendingAction('update-manga');
    setNotice({ title: labels.t('working') });
    const data = new FormData(event.currentTarget);
    try {
      const updated = await api.updateManga(selectedManga.id, {
        name: String(data.get('name') || selectedManga.name),
        homepage: String(data.get('homepage') || ''),
        default_language: String(data.get('default_language') || selectedManga.default_language || DEFAULT_LANGUAGE),
        category: String(data.get('category') || ''),
        tags: uniqueCsv(String(data.get('tags') || ''))
      });
      const nextManga = await api.listManga();
      setManga(nextManga);
      setSelectedManga(nextManga.find((item) => item.id === updated.id) || updated);
      setReadLang(updated.default_language || DEFAULT_LANGUAGE);
      setNotice({ title: labels.t('saveSettings'), body: updated.name });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  function toggleBulkManga(mangaId: string) {
    setSelectedMangaIds((current) => {
      const next = new Set(current);
      if (next.has(mangaId)) {
        next.delete(mangaId);
      } else {
        next.add(mangaId);
      }
      return next;
    });
  }

  async function applyBulkMetadata(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedMangaIds.size) return;
    setPendingAction('bulk-metadata');
    setNotice({ title: labels.t('working') });
    try {
      const ids = Array.from(selectedMangaIds);
      await Promise.all(ids.map((mangaId) => api.updateManga(mangaId, {
        category: bulkCategory,
        tags: uniqueCsv(bulkTags)
      })));
      const nextManga = await api.listManga();
      setManga(nextManga);
      if (selectedManga) {
        setSelectedManga(nextManga.find((item) => item.id === selectedManga.id) || selectedManga);
      }
      setSelectedMangaIds(new Set());
      setNotice({ title: labels.t('saveSettings'), body: formatT(uiLang, 'bulkUpdated', { count: String(ids.length) }) });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function createChapter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedManga) return;
    const data = new FormData(event.currentTarget);
    const created = await api.createChapter(selectedManga.id, {
      title: String(data.get('title') || ''),
      number: String(data.get('number') || ''),
      sort_order: chapters.length + 1
    });
    const next = await api.listChapters(selectedManga.id);
    setChapters(next);
    setSelectedChapter(next.find((chapter) => chapter.id === created.id) || created);
    setRead(null);
    event.currentTarget.reset();
  }

  async function renameChapter(chapter: Chapter) {
    const title = window.prompt(labels.t('chapterTitle'), chapter.title)?.trim();
    if (!title || title === chapter.title) return;
    setPendingAction(`update-chapter-${chapter.id}`);
    try {
      const updated = await api.updateChapter(chapter.id, { title });
      const nextChapters = chapters.map((item) => item.id === updated.id ? updated : item);
      setChapters(nextChapters);
      if (selectedChapter?.id === updated.id) {
        setSelectedChapter(updated);
      }
      setNotice({ title: labels.t('saveSettings'), body: updated.title });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function deleteChapter(chapter: Chapter) {
    if (!selectedManga) return;
    if (!window.confirm(formatT(uiLang, 'confirmDeleteChapter', { name: chapter.title }))) return;
    setPendingAction(`delete-chapter-${chapter.id}`);
    try {
      await api.deleteChapter(chapter.id);
      const nextChapters = await api.listChapters(selectedManga.id);
      setChapters(nextChapters);
      if (selectedChapter?.id === chapter.id) {
        setSelectedChapter(nextChapters[0] || null);
        setRead(null);
        setCurrentPageIndex(0);
      }
      setNotice({ title: labels.t('deleteChapter'), body: chapter.title });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function persistChapterOrder(ordered: Chapter[], reason: string) {
    if (!selectedManga) return;
    setPendingAction('reorder-chapters');
    try {
      const updated = await api.reorderChapters(selectedManga.id, ordered.map((chapter) => chapter.id));
      setChapters(updated);
      addLog(`chapter order saved (${reason}): ${updated.map((chapter) => chapter.title).join(' > ')}`);
      if (read && selectedChapter) {
        setRead(await api.readChapter(selectedChapter.id, readLang, mode));
      }
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  function reorderDraggedChapter(targetChapterId: string) {
    if (!draggedChapterId || draggedChapterId === targetChapterId) return;
    const fromIndex = chapters.findIndex((chapter) => chapter.id === draggedChapterId);
    const toIndex = chapters.findIndex((chapter) => chapter.id === targetChapterId);
    if (fromIndex < 0 || toIndex < 0) return;
    const ordered = chapters.slice();
    const [moved] = ordered.splice(fromIndex, 1);
    ordered.splice(toIndex, 0, moved);
    chaptersRef.current = ordered;
    setChapters(ordered);
  }

  async function finishChapterDrag() {
    if (!draggedChapterId || dragFinishedRef.current) return;
    dragFinishedRef.current = true;
    const ordered = chaptersRef.current.slice();
    setDraggedChapterId('');
    await persistChapterOrder(ordered, 'drag');
  }

  async function openReader(chapter = selectedChapter, nextMode = mode, nextLang = readLang) {
    if (!chapter) return;
    saveReaderProgress();
    setSelectedChapter(chapter);
    setMode(nextMode);
    setReadLang(nextLang);
    setActiveView('reader');
    addLog(`open reader chapter=${chapter.title} id=${chapter.id} lang=${nextLang} default=${selectedManga?.default_language || ''} mode=${nextMode}`);
    const response = await api.readChapter(chapter.id, nextLang, nextMode);
    const savedProgress = loadReaderProgress(chapter.id, nextLang, nextMode);
    pendingReaderRestoreRef.current = savedProgress;
    setFailedImageIds(new Set());
    setCurrentPageIndex(nextMode === 'page' ? Math.min(savedProgress.pageIndex, Math.max(0, response.pages.length - 1)) : 0);
    setRead(response);
    const missing = response.pages.filter((page) => page.missing).length;
    addLog(`read response chapter=${response.chapter_id} lang=${response.language} pages=${response.pages.length} missing=${missing}`);
    response.pages.slice(0, 20).forEach((page) => {
      addLog(`page ${page.page_index} image=${page.image_id} status=${page.status} missing=${page.missing} url=${page.url}`);
    });
  }

  async function toggleReaderFullscreen() {
    const element = readerRef.current;
    if (!element) return;
    try {
      if (document.fullscreenElement === element) {
        await document.exitFullscreen();
        addLog('reader fullscreen exited');
      } else {
        await element.requestFullscreen();
        addLog('reader fullscreen entered');
      }
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    }
  }

  function moveReaderPage(direction: -1 | 1) {
    if (!read) return;
    setCurrentPageIndex((index) => Math.max(0, Math.min(read.pages.length - 1, index + direction)));
  }

  function taskSummary(task: { id?: string; status?: string; total?: number; completed?: number; failed?: number; error?: string }) {
    const lines = [
      formatT(uiLang, 'translationDetails', { source: sourceLang, target: targetLang, model: modelId })
    ];
    if (task.status) lines.push(formatT(uiLang, 'taskStatus', { status: task.status }));
    if (typeof task.total === 'number') {
      lines.push(formatT(uiLang, 'taskProgress', {
        completed: String(task.completed ?? 0),
        total: String(task.total),
        failed: String(task.failed ?? 0)
      }));
    }
    if (task.id) lines.push(formatT(uiLang, 'taskId', { id: task.id }));
    if (task.error) lines.push(task.error);
    return lines.join('\n');
  }

  async function logTranslationTaskEvents(taskId: string) {
    try {
      const events = await api.getTranslationTaskEvents(taskId);
      const taskSignature = `task:${events.status}:${events.completed}:${events.failed}:${events.total}:${events.message || ''}`;
      if (translationEventSignaturesRef.current[`${taskId}:task`] !== taskSignature) {
        translationEventSignaturesRef.current[`${taskId}:task`] = taskSignature;
        addLog(`translation ${taskId}: ${events.status} ${events.completed}/${events.total}, failed=${events.failed}${events.message ? `, ${events.message}` : ''}`);
      }
      for (const item of events.items) {
        const signature = `${item.status}:${item.message || ''}:${item.translated ? '1' : '0'}:${item.translated_url || ''}`;
        const key = `${taskId}:${item.image_id}`;
        if (translationEventSignaturesRef.current[key] === signature) continue;
        translationEventSignaturesRef.current[key] = signature;
        addLog(`page ${item.page_index} ${item.filename}: ${item.status}${item.message ? `, ${item.message}` : ''}`);
      }
    } catch (error) {
      addLog(`translation log fetch failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function translateChapter() {
    await runTranslation('chapter');
  }

  async function translateManga() {
    await runTranslation('manga');
  }

  async function translateImage(imageId: string) {
    await runTranslation('image', imageId);
  }

  function translationPayload(): TranslatePayload {
    return {
      source_language: sourceLang,
      target_language: targetLang,
      model_id: modelId,
      font_id: fontId,
      user_id: translationCreds?.user_id,
      email: translationCreds?.email,
      access_token: translationCreds?.access_token,
      raw_cookie: translationCreds?.raw_cookie,
      base_url: translationCreds?.base_url || translationBaseUrl,
      concurrency: translationConcurrency
    };
  }

  async function pollTranslationTask(taskId: string) {
    setNotice((current) => current ? { ...current, body: `${current.body || ''}\n${labels.t('pollingTask')}`.trim() } : current);
    await logTranslationTaskEvents(taskId);
    for (let attempt = 0; attempt < 600; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      const task = await api.getTranslationTask(taskId);
      await logTranslationTaskEvents(taskId);
      setNotice({
        title: labels.t('translationStarted'),
        body: taskSummary(task)
      });
      if (task.status === 'completed' || task.status === 'failed') {
        const nextReadLang = task.status === 'completed' ? task.target_language || targetLang || readLang : readLang;
        addLog(`translation task ${task.status}: id=${taskId} target=${task.target_language || targetLang || ''}; refresh reader lang=${nextReadLang}`);
        if (selectedChapter) await openReader(selectedChapter, mode, nextReadLang);
        break;
      }
    }
    addLog(`translation task polling stopped: id=${taskId}`);
  }

  async function runTranslation(scope: 'chapter' | 'manga' | 'image', imageId = '') {
    if ((scope === 'chapter' && !selectedChapter) || (scope === 'manga' && !selectedManga) || (scope === 'image' && !imageId)) return;
    setPendingAction(`translate-${scope}`);
    setNotice({ title: labels.t('working') });
    try {
      const payload = translationPayload();
      const task = scope === 'chapter'
        ? await api.translateChapter(selectedChapter!.id, payload)
        : scope === 'manga'
          ? await api.translateManga(selectedManga!.id, payload)
          : await api.translateImage(imageId, payload);
      setNotice({
        title: labels.t('translationStarted'),
        body: taskSummary(task)
      });
      addLog(`translation task submitted: id=${task.id || ''} scope=${scope} source=${payload.source_language} target=${payload.target_language} model=${payload.model_id} concurrency=${payload.concurrency}`);
      if (task.id) {
        translationEventSignaturesRef.current = {};
        void pollTranslationTask(task.id);
      }
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  async function exportChapter() {
    if (!selectedChapter) return;
    await runExport('chapter');
  }

  async function exportManga() {
    if (!selectedManga) return;
    await runExport('manga');
  }

  async function runExport(scope: 'chapter' | 'manga') {
    if ((scope === 'chapter' && !selectedChapter) || (scope === 'manga' && !selectedManga)) return;
    setPendingAction(`export-${scope}`);
    setNotice({ title: labels.t('working') });
    try {
      const task = scope === 'chapter'
        ? await api.exportChapter(selectedChapter!.id, { language: readLang, image_format: format, skip_missing: false })
        : await api.exportManga(selectedManga!.id, { language: readLang, image_format: format, skip_missing: false });
      const href = task.id ? `/api/exports/download/${task.id}` : undefined;
      const scopeLabel = labels.t(scope === 'chapter' ? 'exportScopeChapter' : 'exportScopeManga');
      setNotice({
        title: labels.t('exportReady'),
        body: formatT(uiLang, 'exportDetails', { scope: scopeLabel, status: task.status || 'completed' }),
        href,
        hrefLabel: labels.t('downloadExport')
      });
    } catch (error) {
      setNotice({ title: labels.t('actionFailed'), body: error instanceof Error ? error.message : String(error) });
    } finally {
      setPendingAction('');
    }
  }

  if (!unlocked) {
    return (
      <main className="auth-shell">
        <form className="auth-panel" onSubmit={unlock}>
          <div className="auth-brand">
            <img src="/logo.svg" alt="" />
            <div>
              <div className="brand-name">{labels.t('app')}</div>
              <div className="version-pill">v{APP_VERSION}</div>
            </div>
          </div>
          <label>{labels.t('password')}</label>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoFocus />
          <button type="submit"><Play size={16} /> {labels.t('unlock')}</button>
          <select value={uiLang} onChange={(event) => setUiLang(event.target.value as UiLang)}>
            {uiLanguages.map((item) => <option key={item.code} value={item.code}>{languageOptionLabel(item.code, uiLang)}</option>)}
          </select>
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <img className="logo-mark" src="/logo.svg" alt="" />
          <span>{labels.t('app')}</span>
          <span className="version-pill">v{APP_VERSION}</span>
        </div>
        <nav className="app-nav" aria-label="Primary">
          <button type="button" className={activeView === 'settings' ? 'nav-button active' : 'nav-button'} onClick={() => switchView('settings')}>
            <Settings size={16} /> {labels.t('settings')}
          </button>
          <button type="button" className={activeView === 'manga' ? 'nav-button active' : 'nav-button'} onClick={() => switchView('manga')}>
            <Library size={16} /> {labels.t('mangaPage')}
          </button>
          <button type="button" className={activeView === 'reader' ? 'nav-button active' : 'nav-button'} onClick={() => switchView('reader')}>
            <BookOpen size={16} /> {labels.t('reader')}
          </button>
        </nav>
        <div className="top-actions">
          <span className={translationConnected ? 'status-dot ok' : 'status-dot'}>{translationConnected ? labels.t('translationConnected') : labels.t('translationAccount')}</span>
          <Languages size={18} />
          <select value={uiLang} onChange={(event) => setUiLang(event.target.value as UiLang)}>
            {uiLanguages.map((item) => <option key={item.code} value={item.code}>{languageOptionLabel(item.code, uiLang)}</option>)}
          </select>
        </div>
      </header>

      <section className={activeView === 'manga' ? 'workspace' : 'workspace single-workspace'}>
        {activeView === 'manga' && <aside className="sidebar">
          <h2>{labels.t('library')}</h2>
          <div className="sidebar-meta">{manga.length} manga · {chapters.length} chapters</div>
          <section className="sidebar-section">
            <h3>{labels.t('newManga')}</h3>
            {isDesktopRuntime() && (
              <button className="file-button secondary folder-picker" type="button" onClick={importMangaFolderFromDesktop} disabled={pendingAction === 'import-folder'}>
                <FolderOpen size={16} /> {labels.t('importFolder')}
              </button>
            )}
            {!isDesktopRuntime() && (
              <label className="file-button secondary folder-picker">
                <FolderOpen size={16} /> {labels.t('importFolder')}
                <input
                  type="file"
                  multiple
                  {...({ webkitdirectory: 'true' } as any)}
                  onChange={importMangaFolder}
                />
              </label>
            )}
            <form className="stack" onSubmit={createManga}>
              <input name="name" placeholder={labels.t('mangaName')} required />
              <select name="default_language" value={createLanguage} onChange={(event) => setCreateLanguage(event.target.value)} aria-label={labels.t('defaultLanguage')}>
                {mangaLanguageOptions.map((lang) => (
                  <option key={lang} value={lang}>{languageOptionLabel(lang, uiLang)}</option>
                ))}
              </select>
              <input name="category" list="category-options" value={createCategory} onChange={(event) => setCreateCategory(event.target.value)} placeholder={labels.t('category')} />
              <input name="tags" list="tag-options" value={createTags} onChange={(event) => setCreateTags(event.target.value)} placeholder={labels.t('tags')} />
              <label className="file-button cover-picker">
                <Upload size={16} /> {labels.t('coverImage')}
                <input
                  type="file"
                  accept="image/*"
                  onChange={(event) => setCoverFile(event.currentTarget.files?.[0] || null)}
                />
              </label>
              {coverFile && <div className="file-hint">{coverFile.name}</div>}
              <button type="submit" disabled={pendingAction === 'create-manga'}><FolderPlus size={16} /> {labels.t('createManga')}</button>
            </form>
          </section>
          <section className="sidebar-section">
            <h3>{labels.t('findManga')}</h3>
            <input value={mangaSearch} onChange={(event) => setMangaSearch(event.target.value)} placeholder={labels.t('searchByName')} />
            <select value={mangaCategoryFilter} onChange={(event) => setMangaCategoryFilter(event.target.value)}>
              <option value="">{labels.t('allCategories')}</option>
              {categoryList.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
            <select value={mangaTagFilter} onChange={(event) => setMangaTagFilter(event.target.value)}>
              <option value="">{labels.t('allTags')}</option>
              {tagList.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
            </select>
          </section>
          <div className="list">
            {filteredManga.map((item) => (
              <div className="library-item" key={item.id}>
                <button className={selectedManga?.id === item.id ? 'row active' : 'row'} onClick={() => loadChapters(item)}>
                  <span>{item.name}</span>
                  {(item.category || item.tags) && <small>{[item.category, item.tags].filter(Boolean).join(' · ')}</small>}
                </button>
                <button
                  type="button"
                  className="icon-button danger"
                  title={labels.t('deleteManga')}
                  aria-label={labels.t('deleteManga')}
                  onClick={() => deleteManga(item)}
                  disabled={pendingAction === `delete-manga-${item.id}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
            {!manga.length && <div className="empty-state">{labels.t('createManga')}</div>}
            {Boolean(manga.length && !filteredManga.length) && <div className="empty-state">{labels.t('noMangaFound')}</div>}
          </div>
        </aside>}

        <section className="main-panel">
          <datalist id="category-options">
            {categoryList.map((item) => <option key={item} value={item} />)}
          </datalist>
          <datalist id="tag-options">
            {tagList.map((item) => <option key={item} value={item} />)}
          </datalist>
          {activeView === 'settings' && (
            <section className="settings-page">
              <div className="settings-grid">
                <form className="settings-panel" onSubmit={(event) => {
                  event.preventDefault();
                  setCategoryOptions(uniqueCsv(categoryOptions));
                  setTagOptions(uniqueCsv(tagOptions));
                  setNotice({ title: labels.t('saveSettings') });
                }}>
                  <h2>{labels.t('librarySettings')}</h2>
                  <label>
                    <span>{labels.t('categoryNames')}</span>
                    <textarea value={categoryOptions} onChange={(event) => setCategoryOptions(event.target.value)} placeholder={labels.t('categoryNames')} />
                  </label>
                  <label>
                    <span>{labels.t('tagNames')}</span>
                    <textarea value={tagOptions} onChange={(event) => setTagOptions(event.target.value)} placeholder={labels.t('tagNames')} />
                  </label>
                  <button type="submit"><Tags size={16} /> {labels.t('saveSettings')}</button>
                </form>

                <form className="settings-panel settings-panel-wide" onSubmit={applyBulkMetadata}>
                  <h2>{labels.t('bulkMetadata')}</h2>
                  <div className="bulk-manga-list">
                    {manga.map((item) => (
                      <label className="bulk-manga-item" key={item.id}>
                        <input
                          type="checkbox"
                          checked={selectedMangaIds.has(item.id)}
                          onChange={() => toggleBulkManga(item.id)}
                        />
                        <span>
                          <strong>{item.name}</strong>
                          <small>{[item.category, item.tags].filter(Boolean).join(' · ') || labels.t('uncategorized')}</small>
                        </span>
                      </label>
                    ))}
                    {!manga.length && <div className="empty-state">{labels.t('createManga')}</div>}
                  </div>
                  <input list="category-options" value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)} placeholder={labels.t('category')} />
                  <input list="tag-options" value={bulkTags} onChange={(event) => setBulkTags(event.target.value)} placeholder={labels.t('tags')} />
                  <button type="submit" disabled={!selectedMangaIds.size || pendingAction === 'bulk-metadata'}>
                    <Tags size={16} /> {formatT(uiLang, 'applyToSelected', { count: String(selectedMangaIds.size) })}
                  </button>
                </form>

                {catalogs && (
                  <form className="settings-panel" onSubmit={connectTranslation}>
                    <h2>{labels.t('translationAccount')}</h2>
                    <input value={translationEmail} onChange={(event) => setTranslationEmail(event.target.value)} placeholder={labels.t('translationEmail')} />
                    <input type="password" value={translationPassword} onChange={(event) => setTranslationPassword(event.target.value)} placeholder={labels.t('translationPassword')} />
                    <input value={translationBaseUrl} onChange={(event) => setTranslationBaseUrl(event.target.value)} placeholder={labels.t('translationBaseUrl')} />
                    <div className="settings-row">
                      <button disabled={pendingAction === 'translation-login'}>{labels.t('connectTranslation')}</button>
                      {isDesktopRuntime() && (
                        <button type="button" className="secondary" onClick={connectBrowserTranslation} disabled={pendingAction === 'translation-browser-login'}>
                          {labels.t('browserLogin')}
                        </button>
                      )}
                    </div>
                    {translationConnected && <span className="account-chip">{translationCreds?.email || translationCreds?.user_id}</span>}
                  </form>
                )}

                {catalogs && (
                  <div className="settings-panel">
                    <h2>{labels.t('translationSettings')}</h2>
                    <select value={sourceLang} onChange={(event) => setSourceLang(event.target.value)}>
                      {catalogs.sourceLanguages.map((lang) => <option key={lang} value={lang}>{languageOptionLabel(lang, uiLang)}</option>)}
                    </select>
                    <select value={targetLang} onChange={(event) => setTargetLang(event.target.value)}>
                      {catalogs.targetLanguages.map((lang) => <option key={lang} value={lang}>{languageOptionLabel(lang, uiLang)}</option>)}
                    </select>
                    <select value={modelId} onChange={(event) => setModelId(event.target.value)}>
                      {catalogs.models.items.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}
                    </select>
                    <select value={fontId} onChange={(event) => setFontId(event.target.value)}>
                      {catalogs.fonts.items.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}
                    </select>
                    <label className="inline-field">
                      <span>{labels.t('translationConcurrency')}</span>
                      <input
                        type="number"
                        min={MIN_TRANSLATION_CONCURRENCY}
                        max={MAX_TRANSLATION_CONCURRENCY}
                        step={1}
                        value={translationConcurrency}
                        onChange={(event) => setTranslationConcurrency(clampTranslationConcurrency(event.target.value))}
                      />
                    </label>
                  </div>
                )}
              </div>
            </section>
          )}

          {activeView === 'manga' && (
            <>
          <div className="chapter-tools">
            <div>
              <h2>{selectedManga?.name || labels.t('chapters')}</h2>
              {selectedManga && (
                <div className="context-line">
                  {languageOptionLabel(selectedManga.default_language, uiLang)}
                  {selectedManga.category ? ` · ${selectedManga.category}` : ''}
                  {selectedManga.tags ? ` · ${selectedManga.tags}` : ''}
                </div>
              )}
              <form className="inline" onSubmit={createChapter}>
                <input name="title" placeholder={labels.t('chapterTitle')} required />
                <button>{labels.t('addChapter')}</button>
              </form>
            </div>
            <div className="summary-strip">
              <div><strong>{chapters.length}</strong><span>{labels.t('chapters')}</span></div>
              <div><strong>{read?.pages.length || 0}</strong><span>{labels.t('reader')}</span></div>
              <div><strong>{translatedPages}</strong><span>{labels.t('targetLanguage')}</span></div>
              <div><strong>{missingPages}</strong><span>{labels.t('missingTranslation')}</span></div>
            </div>
          </div>

          {selectedManga && (
            <form className="manga-editor" key={selectedManga.id} onSubmit={updateSelectedManga}>
              <input name="name" defaultValue={selectedManga.name} placeholder={labels.t('mangaName')} required />
              <input name="homepage" defaultValue={selectedManga.homepage} placeholder={labels.t('homepage')} />
              <select name="default_language" defaultValue={selectedManga.default_language} aria-label={labels.t('defaultLanguage')}>
                {mangaLanguageOptions.map((lang) => (
                  <option key={lang} value={lang}>{languageOptionLabel(lang, uiLang)}</option>
                ))}
              </select>
              <input name="category" list="category-options" defaultValue={selectedManga.category || ''} placeholder={labels.t('category')} />
              <input name="tags" list="tag-options" defaultValue={selectedManga.tags || ''} placeholder={labels.t('tags')} />
              <button type="submit" disabled={pendingAction === 'update-manga'}>{labels.t('saveManga')}</button>
            </form>
          )}

          <div className="chapter-list">
            {chapters.map((chapter) => (
              <div
                className={draggedChapterId === chapter.id ? 'chapter-item dragging' : 'chapter-item'}
                key={chapter.id}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = 'move';
                  event.dataTransfer.setData('text/plain', chapter.id);
                  dragFinishedRef.current = false;
                  setDraggedChapterId(chapter.id);
                  addLog(`chapter drag start: ${chapter.title}`);
                }}
                onDragEnter={(event) => {
                  event.preventDefault();
                  reorderDraggedChapter(chapter.id);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = 'move';
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  void finishChapterDrag();
                }}
                onDragEnd={() => {
                  void finishChapterDrag();
                }}
              >
                <span className="drag-handle" title={labels.t('dragChapter')} aria-label={labels.t('dragChapter')}>
                  <GripVertical size={16} />
                </span>
                <button className={selectedChapter?.id === chapter.id ? 'chip active' : 'chip'} onClick={() => openReader(chapter)}>
                  {chapter.title}
                </button>
                <button
                  type="button"
                  className="icon-button"
                  title={labels.t('editChapter')}
                  aria-label={labels.t('editChapter')}
                  draggable={false}
                  onClick={(event) => {
                    event.stopPropagation();
                    void renameChapter(chapter);
                  }}
                  onMouseDown={(event) => event.stopPropagation()}
                  disabled={pendingAction === `update-chapter-${chapter.id}`}
                >
                  <Pencil size={14} />
                </button>
                <button
                  type="button"
                  className="icon-button danger"
                  title={labels.t('deleteChapter')}
                  aria-label={labels.t('deleteChapter')}
                  draggable={false}
                  onClick={(event) => {
                    event.stopPropagation();
                    void deleteChapter(chapter);
                  }}
                  onMouseDown={(event) => event.stopPropagation()}
                  disabled={pendingAction === `delete-chapter-${chapter.id}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
            {selectedManga && !chapters.length && <div className="empty-state wide">{labels.t('addChapter')}</div>}
          </div>

          {selectedChapter && (
            <div className="toolband">
              <label className="file-button">
                <Upload size={16} /> {labels.t('uploadImages')}
                <input type="file" multiple accept="image/*" onChange={async (event) => {
                  if (event.target.files) {
                    await api.uploadImages(selectedChapter.id, event.target.files);
                    await openReader(selectedChapter);
                  }
                }} />
              </label>
              <select value={format} onChange={(event) => setFormat(event.target.value)}>
                {(catalogs?.outputFormats || ['webp', 'jpg', 'png']).map((item) => <option key={item}>{item}</option>)}
              </select>
              <button onClick={exportChapter} disabled={pendingAction === 'export-chapter'}><Download size={16} /> {labels.t('exportChapter')}</button>
              <button onClick={exportManga} disabled={pendingAction === 'export-manga'}><Download size={16} /> {labels.t('exportManga')}</button>
            </div>
          )}

          {selectedManga && catalogs && (
            <div className="translate-bar">
              <span className={translationConnected ? 'status-dot ok' : 'status-dot'}>{translationConnected ? labels.t('translationConnected') : labels.t('translationAccount')}</span>
              <span className="context-line inline-context">{formatT(uiLang, 'translationDetails', { source: sourceLang, target: targetLang, model: modelId })}</span>
              <button onClick={translateChapter} disabled={!selectedChapter || pendingAction === 'translate-chapter'}>{labels.t('translateChapter')}</button>
              <button onClick={translateManga} disabled={pendingAction === 'translate-manga'}>{labels.t('translateManga')}</button>
            </div>
          )}

            </>
          )}

          {notice && (
            <div className="notice" role="status">
              <strong>{notice.title}</strong>
              {notice.body && <span>{notice.body}</span>}
              {notice.href && (
                <a className="download-link" href={notice.href}>
                  <ExternalLink size={16} /> {notice.hrefLabel || notice.href}
                </a>
              )}
            </div>
          )}

          <section className="log-panel">
            <div className="log-header">
              <h3>{labels.t('logs')}</h3>
              <span>{logs.length}</span>
            </div>
            <div className="log-lines" role="log" aria-live="polite">
              {logs.length ? logs.slice(-80).map((line, index) => <div key={`${index}-${line}`}>{line}</div>) : <div className="log-empty">{labels.t('noLogs')}</div>}
            </div>
          </section>

          {activeView === 'reader' && <section
            ref={readerRef}
            className={`${mode === 'strip' ? 'reader strip-reader' : 'reader page-reader'}${fullscreenReader ? ' fullscreen-reader' : ''}${readerChromeVisible ? ' reader-chrome-visible' : ''}`}
            onMouseMove={handleReaderMouseMove}
            onScroll={() => {
              if (mode === 'strip') saveReaderProgress();
            }}
          >
            {selectedChapter && (
              <div className="reader-nav" onFocus={showReaderChrome} onMouseMove={showReaderChrome} onMouseDown={showReaderChrome}>
                <div className="reader-nav-row reader-options-row">
                  <select className="reader-language-select" value={readLang} onChange={(event) => openReader(selectedChapter, mode, event.target.value)}>
                    {readLanguageOptions.map((lang) => (
                      <option key={lang} value={lang}>
                        {lang === defaultReadLanguage ? `${languageOptionLabel(lang, uiLang)} (${labels.t('defaultLanguage')})` : languageOptionLabel(lang, uiLang)}
                      </option>
                    ))}
                  </select>
                  <select className="reader-mode-select" value={mode} onChange={(event) => openReader(selectedChapter, event.target.value as Mode, readLang)}>
                    <option value="strip">{labels.t('strip')}</option>
                    <option value="page">{labels.t('page')}</option>
                  </select>
                  <button type="button" className="secondary" onClick={toggleReaderFullscreen}>
                    {fullscreenReader ? <Minimize2 size={16} /> : <Maximize2 size={16} />} {labels.t('fullscreenReader')}
                  </button>
                </div>
                <div className="reader-nav-row reader-chapter-row">
                  <button className="secondary" onClick={() => previousChapter && openReader(previousChapter)} disabled={!previousChapter}>
                    <ChevronLeft size={16} /> {labels.t('previousChapter')}
                  </button>
                  <select
                    className="reader-chapter-select"
                    value={selectedChapter.id}
                    onChange={(event) => {
                      const chapter = chapters.find((item) => item.id === event.target.value);
                      if (chapter) void openReader(chapter, mode, readLang);
                    }}
                    aria-label={labels.t('jumpToChapter')}
                  >
                    {chapters.map((chapter) => (
                      <option key={chapter.id} value={chapter.id}>{chapter.title}</option>
                    ))}
                  </select>
                  <button className="secondary" onClick={() => nextChapter && openReader(nextChapter)} disabled={!nextChapter}>
                    {labels.t('nextChapter')} <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}
            {read && (
              <div className="reader-pages">
                {mode === 'page' && (
                  <button type="button" className="page-turn page-turn-prev" onClick={() => moveReaderPage(-1)} disabled={!canGoPreviousPage} aria-label={labels.t('previousPage')}>
                    <ChevronLeft size={24} />
                  </button>
                )}
                {readerPages.map((page) => {
                  const unavailable = page.missing || failedImageIds.has(page.image_id);
                  return (
                    <figure className={unavailable ? 'page missing' : 'page'} key={page.image_id}>
                      {unavailable ? (
                        <div className="missing-card">
                          <button className="image-translate" onClick={() => translateImage(page.image_id)} disabled={pendingAction === 'translate-image'}>
                            {labels.t('translateImage')}
                          </button>
                          <BookOpen size={28} />
                          <strong>{labels.t('missingTranslation')}</strong>
                          <span>Page {page.page_index} · {page.status}</span>
                        </div>
                      ) : (
                        <img
                          src={page.url}
                          alt={`page ${page.page_index}`}
                          onLoad={(event) => {
                            const image = event.currentTarget;
                            addLog(`image loaded page=${page.page_index} image=${page.image_id} status=${page.status} missing=${page.missing} natural=${image.naturalWidth}x${image.naturalHeight} url=${page.url}`);
                          }}
                          onError={() => {
                            addLog(`image failed page=${page.page_index} image=${page.image_id} status=${page.status} missing=${page.missing} url=${page.url}`);
                            setFailedImageIds((current) => {
                              const next = new Set(current);
                              next.add(page.image_id);
                              return next;
                            });
                          }}
                        />
                      )}
                    </figure>
                  );
                })}
                {mode === 'page' && (
                  <button type="button" className="page-turn page-turn-next" onClick={() => moveReaderPage(1)} disabled={!canGoNextPage} aria-label={labels.t('nextPage')}>
                    <ChevronRight size={24} />
                  </button>
                )}
              </div>
            )}
            {!read && selectedChapter && (
              <div className="reader-empty">
                <BookOpen size={30} />
                <span>{labels.t('openReader')}</span>
              </div>
            )}
          </section>}
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

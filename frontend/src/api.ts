export type Manga = {
  id: string;
  name: string;
  homepage: string;
  default_language: string;
  cover_image_id: string;
  category: string;
  tags: string;
  created_at: string;
};

export type Chapter = {
  id: string;
  manga_id: string;
  title: string;
  number: string;
  sort_order: number;
};

export type ReadPage = {
  image_id: string;
  page_index: number;
  url: string;
  status: string;
  language: string;
  missing: boolean;
};

export type ReadResponse = {
  chapter_id: string;
  mode: 'strip' | 'page';
  language: string;
  pages: ReadPage[];
  previous_chapter_id?: string | null;
  next_chapter_id?: string | null;
};

export type Catalogs = {
  uiLanguages: Array<{ code: string; name: string; dir: string }>;
  sourceLanguages: string[];
  targetLanguages: string[];
  models: { defaultModel: string; items: Array<{ key: string; name: string; credits?: number }> };
  fonts: { defaultStyle: string; items: Array<{ key: string; name: string }> };
  outputFormats: string[];
};

export type TaskResponse = {
  id?: string;
  status?: string;
  total?: number;
  completed?: number;
  failed?: number;
  error?: string;
  file_path?: string;
  source_language?: string;
  target_language?: string;
};

export type TranslationTaskEvents = {
  task_id: string;
  status: string;
  completed: number;
  failed: number;
  total: number;
  message: string;
  items: Array<{
    image_id: string;
    page_index: number;
    filename: string;
    status: string;
    message: string;
    translated: boolean;
    translated_url: string;
  }>;
};

export type TranslationCredentials = {
  user_id: string;
  access_token: string;
  email: string;
  raw_cookie?: string;
  base_url?: string;
};

export type TranslatePayload = {
  source_language: string;
  target_language: string;
  model_id: string;
  font_id: string;
  user_id?: string;
  email?: string;
  access_token?: string;
  raw_cookie?: string;
  base_url?: string;
  proxy_base?: string;
  concurrency?: number;
};

export function isDesktopRuntime(): boolean {
  return typeof window !== 'undefined' && Boolean(window.mangaManager?.isDesktop);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || undefined);
  if (!(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (isDesktopRuntime()) {
    headers.set('X-MangaManager-Client', 'desktop');
  }
  const res = await fetch(path, {
    ...init,
    credentials: 'include',
    headers
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (password: string) => request<{ ok: boolean }>('/api/local/web-auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  translationLogin: (payload: { email: string; password: string; base_url?: string }) =>
    request<TranslationCredentials>('/api/translate/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  translationCookieLogin: (payload: { raw_cookie: string; base_url?: string; user_id?: string; email?: string; access_token?: string }) =>
    request<TranslationCredentials>('/api/translate/auth/cookie', { method: 'POST', body: JSON.stringify(payload) }),
  catalogs: () => request<Catalogs>('/api/translate/catalogs'),
  listManga: () => request<Manga[]>('/api/manga'),
  createManga: (payload: { name: string; homepage: string; default_language: string; category?: string; tags?: string }) => request<Manga>('/api/manga', { method: 'POST', body: JSON.stringify(payload) }),
  updateManga: (mangaId: string, payload: Partial<Pick<Manga, 'name' | 'homepage' | 'default_language' | 'category' | 'tags'>>) =>
    request<Manga>(`/api/manga/${mangaId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteManga: (mangaId: string) => request<{ ok: boolean }>(`/api/manga/${mangaId}`, { method: 'DELETE' }),
  importFolder: (payload: { folder_path: string; default_language: string; max_images?: number }) =>
    request<Manga>('/api/desktop/import-folder', { method: 'POST', body: JSON.stringify(payload) }),
  createMangaWithCover: (payload: { name: string; homepage: string; default_language: string; category?: string; tags?: string; coverImage?: File | null }) => {
    const form = new FormData();
    form.append('name', payload.name);
    form.append('homepage', payload.homepage);
    form.append('default_language', payload.default_language);
    form.append('category', payload.category || '');
    form.append('tags', payload.tags || '');
    if (payload.coverImage) {
      form.append('cover_image', payload.coverImage);
    }
    return request<Manga>('/api/manga/upload', { method: 'POST', body: form });
  },
  uploadMangaCover: (mangaId: string, coverImage: File) => {
    const form = new FormData();
    form.append('cover_image', coverImage);
    return request<Manga>(`/api/manga/${mangaId}/cover`, { method: 'POST', body: form });
  },
  listChapters: (mangaId: string) => request<Chapter[]>(`/api/manga/${mangaId}/chapters`),
  createChapter: (mangaId: string, payload: { title: string; number: string; sort_order: number }) => request<Chapter>(`/api/manga/${mangaId}/chapters`, { method: 'POST', body: JSON.stringify(payload) }),
  updateChapter: (chapterId: string, payload: Partial<Pick<Chapter, 'title' | 'number' | 'sort_order'>>) =>
    request<Chapter>(`/api/chapters/${chapterId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteChapter: (chapterId: string) => request<{ ok: boolean }>(`/api/chapters/${chapterId}`, { method: 'DELETE' }),
  reorderChapters: (mangaId: string, chapterIds: string[]) =>
    request<Chapter[]>(`/api/manga/${mangaId}/chapters/order`, { method: 'PATCH', body: JSON.stringify({ chapter_ids: chapterIds }) }),
  uploadImages: (chapterId: string, files: Iterable<File>) => {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append('files', file));
    return request(`/api/chapters/${chapterId}/images`, { method: 'POST', body: form });
  },
  readChapter: (chapterId: string, lang: string, mode: 'strip' | 'page') => request<ReadResponse>(`/api/chapters/${chapterId}/read?lang=${encodeURIComponent(lang)}&mode=${mode}`),
  translateChapter: (chapterId: string, payload: TranslatePayload) =>
    request<TaskResponse>(`/api/translate/chapter/${chapterId}`, { method: 'POST', body: JSON.stringify(payload) }),
  translateManga: (mangaId: string, payload: TranslatePayload) =>
    request<TaskResponse>(`/api/translate/manga/${mangaId}`, { method: 'POST', body: JSON.stringify(payload) }),
  translateImage: (imageId: string, payload: TranslatePayload) =>
    request<TaskResponse>(`/api/translate/image/${imageId}`, { method: 'POST', body: JSON.stringify(payload) }),
  getTranslationTask: (taskId: string) => request<TaskResponse>(`/api/translate/tasks/${taskId}`),
  getTranslationTaskEvents: (taskId: string) => request<TranslationTaskEvents>(`/api/translate/tasks/${taskId}/events`),
  exportChapter: (chapterId: string, payload: { language: string; image_format: string; skip_missing: boolean }) =>
    request<TaskResponse>(`/api/export/chapter/${chapterId}`, { method: 'POST', body: JSON.stringify(payload) }),
  exportManga: (mangaId: string, payload: { language: string; image_format: string; skip_missing: boolean }) =>
    request<TaskResponse>(`/api/export/manga/${mangaId}`, { method: 'POST', body: JSON.stringify(payload) }),
  mangaCoverUrl: (mangaId: string) => `/api/manga/${mangaId}/cover`
};

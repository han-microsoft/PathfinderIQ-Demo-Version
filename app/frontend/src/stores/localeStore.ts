/**
 * @module localeStore
 *
 * Zustand store for UI language selection.
 *
 * Module role:
 *   Holds the active locale code and persists it to localStorage.
 *   All UI components read the locale via ``useLocaleStore`` (or the
 *   ``useTranslation`` hook) and re-render when it changes.
 *
 * Supported locales:
 *   en (English), ja (Japanese). More can be added by extending
 *   ``SUPPORTED_LOCALES`` and creating the corresponding JSON file
 *   in ``src/locales/``.
 *
 * Collaborators:
 *   - locales/index.ts       — ``translate()`` reads locale bundles
 *   - hooks/useTranslation.ts — convenience hook wrapping this store
 *   - api/client.ts           — sends ``X-User-Language`` header
 *   - Header.tsx              — renders the language dropdown
 *
 * Dependents:
 *   Consumed by every component that displays translatable text.
 */

import { create } from "zustand";

/** ISO 639-1 language codes for supported UI locales. */
export type LocaleCode = "en" | "ja" | "zh";

/** Metadata for each supported locale — label is in the locale's own script. */
export interface LocaleInfo {
  code: LocaleCode;
  label: string;
  englishName: string;
}

/** All locales the UI can switch to. Add entries here + create the JSON file. */
export const SUPPORTED_LOCALES: LocaleInfo[] = [
  { code: "en", label: "English",  englishName: "English" },
  { code: "ja", label: "日本語",    englishName: "Japanese" },
  { code: "zh", label: "中文",      englishName: "Chinese" },
];

/** Load the saved locale from localStorage, defaulting to English. */
function loadLocale(): LocaleCode {
  try {
    const saved = localStorage.getItem("user-language");
    if (saved && SUPPORTED_LOCALES.some((l) => l.code === saved)) {
      return saved as LocaleCode;
    }
  } catch { /* localStorage unavailable — use default */ }
  return "en";
}

interface LocaleState {
  /** Active UI locale code. */
  locale: LocaleCode;
  /** Switch the UI language. Persists to localStorage. */
  setLocale: (code: LocaleCode) => void;
}

export const useLocaleStore = create<LocaleState>((set) => ({
  locale: loadLocale(),
  setLocale: (code) => {
    try { localStorage.setItem("user-language", code); } catch { /* ignore */ }
    set({ locale: code });
  },
}));

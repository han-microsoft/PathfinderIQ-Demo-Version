/**
 * @module locales/index
 *
 * Locale loader and translation function.
 *
 * Module role:
 *   Loads all locale JSON files and provides the ``translate()`` function
 *   that resolves a key for a given locale. Falls back to English when a
 *   key is missing in the target locale — partial translations are safe.
 *
 * Dependents:
 *   - hooks/useTranslation.ts — wraps translate() with Zustand binding
 *   - Any module that needs translation outside React (stores, utils)
 */

import en from "./en.json";
import ja from "./ja.json";
import zh from "./zh.json";
import type { LocaleCode } from "@/stores/localeStore";

// All locale message bundles keyed by language code.
// Add new locales here as they are created.
const MESSAGES: Record<string, Record<string, string>> = {
  en,
  ja,
  zh,
};

/**
 * Translate a key for the given locale.
 * Falls back to English if the key is missing in the target locale.
 * Returns the raw key if it is missing from all locales (development aid).
 *
 * Supports simple ``{placeholder}`` interpolation via optional ``params``.
 *
 * @param locale - ISO 639-1 language code (e.g. "en", "ja")
 * @param key    - Dot-namespaced translation key (e.g. "chat.placeholder")
 * @param params - Optional key-value replacements for ``{placeholder}`` tokens
 * @returns The translated string, or the raw key if not found anywhere.
 */
export function translate(
  locale: LocaleCode,
  key: string,
  params?: Record<string, string | number>,
): string {
  let text = MESSAGES[locale]?.[key] ?? MESSAGES.en[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}

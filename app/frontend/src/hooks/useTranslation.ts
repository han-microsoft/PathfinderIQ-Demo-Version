/**
 * @module useTranslation
 *
 * React hook for UI text translation.
 *
 * Module role:
 *   Returns a ``t(key, params?)`` function bound to the active locale.
 *   Components that call this hook automatically re-render when the
 *   user switches languages via the sidebar dropdown.
 *
 * Usage:
 *   ```tsx
 *   const { t } = useTranslation();
 *   return <button>{t("chat.sendMessage")}</button>;
 *   ```
 *
 * Collaborators:
 *   - stores/localeStore.ts — provides the active locale code
 *   - locales/index.ts      — provides the translate() implementation
 *
 * Dependents:
 *   Used by every component that renders translatable text.
 */

import { useLocaleStore } from "@/stores/localeStore";
import { translate } from "@/locales";
import type { LocaleCode } from "@/stores/localeStore";

/**
 * Hook returning the translation function and active locale.
 *
 * The returned ``t`` function looks up the key in the active locale's
 * JSON bundle and falls back to English for missing keys.
 */
export function useTranslation(): {
  t: (key: string, params?: Record<string, string | number>) => string;
  locale: LocaleCode;
} {
  const locale = useLocaleStore((s) => s.locale);
  return {
    t: (key: string, params?: Record<string, string | number>) =>
      translate(locale, key, params),
    locale,
  };
}

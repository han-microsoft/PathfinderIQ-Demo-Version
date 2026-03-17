/**
 * Theme context — multi-theme state management.
 *
 * Supports 6 themes: default (Fabric Light + dual logos), fabric-dark,
 * fabric-light, foundry-purple, azure, classic-microsoft.
 * Applies [data-theme] attribute on <html> to activate CSS variable
 * blocks in index.css. Persists to localStorage.
 */
import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

export type ThemeName =
  | "default"
  | "fabric-dark"
  | "fabric-light"
  | "foundry-purple"
  | "azure"
  | "classic-microsoft";

export interface ThemeMeta {
  id: ThemeName;
  label: string;
  icon: string;
  logo: string;
}

export const THEMES: ThemeMeta[] = [
  { id: "default",           label: "Default",           icon: "\u{1F310}", logo: "/images/azure-logo.png" },
  { id: "fabric-dark",       label: "Fabric Dark",       icon: "\u{1F319}", logo: "/images/fabric-logo.png" },
  { id: "fabric-light",      label: "Fabric Light",      icon: "\u2600\uFE0F", logo: "/images/fabric-logo.png" },
  { id: "foundry-purple",    label: "Foundry Purple",    icon: "\u{1F7E3}", logo: "/images/foundry-logo.png" },
  { id: "azure",             label: "Azure",             icon: "\u{1F535}", logo: "/images/azure-logo.png" },
  { id: "classic-microsoft", label: "Classic Microsoft",  icon: "\u{1FA9F}", logo: "/images/microsoft-logo.png" },
];

interface ThemeContextValue {
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
  currentMeta: ThemeMeta;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "default",
  setTheme: () => {},
  currentMeta: THEMES[0],
});

export function useTheme() {
  return useContext(ThemeContext);
}

const STORAGE_KEY = 'app-theme';
const VALID_THEMES = new Set<string>(THEMES.map((t) => t.id));

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && VALID_THEMES.has(stored)) return stored as ThemeName;
    } catch {}
    return "default";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.classList.remove("dark");
    try { localStorage.setItem(STORAGE_KEY, theme); } catch {}
  }, [theme]);

  const setTheme = (t: ThemeName) => {
    if (VALID_THEMES.has(t)) setThemeState(t);
  };

  const currentMeta = THEMES.find((t) => t.id === theme) ?? THEMES[0];

  return (
    <ThemeContext.Provider value={{ theme, setTheme, currentMeta }}>
      {children}
    </ThemeContext.Provider>
  );
}

'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { normalizeTheme, resolveTheme, themeKey } from '@/lib/theme.mjs';
type Preference = 'system' | 'light' | 'dark';
const Context = createContext<{ preference: Preference; choose: (value: Preference) => void; storageError: boolean }>({ preference: 'system', choose() {}, storageError: false });
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreference] = useState<Preference>('system');
  const [storageError, setStorageError] = useState(false);
  useEffect(() => {
    try { setPreference(normalizeTheme(localStorage.getItem(themeKey))); } catch { setStorageError(true); }
    const sync = (event: StorageEvent) => { if (event.key === themeKey || event.key === null) setPreference(normalizeTheme(event.newValue)); };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)');
    const apply = () => { const theme = resolveTheme(preference, media.matches); document.documentElement.dataset.theme = theme; document.documentElement.style.colorScheme = theme; };
    apply(); media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [preference]);
  function choose(value: Preference) { setPreference(value); try { localStorage.setItem(themeKey, value); setStorageError(false); } catch { setStorageError(true); } }
  return <Context.Provider value={{ preference, choose, storageError }}>{children}<div className="theme-dock"><ThemeControl /></div></Context.Provider>;
}
export function ThemeControl() {
  const { preference, choose, storageError } = useContext(Context);
  return <label className="theme-control"><span>外观</span><select aria-label="外观主题" value={preference} onChange={e => choose(e.target.value as Preference)}><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select>{storageError && <small role="status">本次切换有效，无法记住选择</small>}</label>;
}

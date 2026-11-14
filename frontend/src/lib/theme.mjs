export const themeKey = 'finsentinel.theme.v1';
export function normalizeTheme(value) { return ['light', 'dark', 'system'].includes(value) ? value : 'system'; }
export function resolveTheme(value, systemDark) { const preference = normalizeTheme(value); return preference === 'system' ? (systemDark ? 'dark' : 'light') : preference; }
export const themeBootstrap = `(function(){var p='system';try{p=localStorage.getItem('${themeKey}')||'system'}catch(e){}var d=p==='dark'||(p!=='light'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=d?'dark':'light';document.documentElement.style.colorScheme=d?'dark':'light'})()`;

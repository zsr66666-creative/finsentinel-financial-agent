import type { Metadata } from 'next';
import './globals.css';
import './macos.css';
import './portal.css';
import { ResearchCatalogProvider } from '@/components/research-catalog';
import { ThemeProvider } from '@/components/theme-provider';
import { themeBootstrap } from '@/lib/theme.mjs';
import { SessionProvider } from '@/components/demo-session';
export const metadata: Metadata = { title: 'FinSentinel · 证据链风险研判', description: '上市公司财报、原文证据与财务核对研究门户' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeBootstrap }} /></head><body><ThemeProvider><SessionProvider><ResearchCatalogProvider>{children}</ResearchCatalogProvider></SessionProvider></ThemeProvider></body></html>;
}

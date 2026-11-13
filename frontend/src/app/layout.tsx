import type { Metadata } from 'next';
import './globals.css';
import { DemoSession } from '@/components/demo-session';
export const metadata: Metadata = { title: 'FinSentinel · 证据链风险研判', description: '消费电子财报与公告研究工作台' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body><DemoSession>{children}</DemoSession></body></html>;
}

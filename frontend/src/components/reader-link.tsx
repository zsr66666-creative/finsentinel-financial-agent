import Link from 'next/link';
import { readerHref, type ReaderLocator } from '@/lib/reader.mjs';
export function ReaderLink({locator,children}:{locator:ReaderLocator;children?:React.ReactNode}) { const href=readerHref(locator);return href?<Link className="portal-text-link" href={href}>{children??'阅读报告原文 →'}</Link>:null; }

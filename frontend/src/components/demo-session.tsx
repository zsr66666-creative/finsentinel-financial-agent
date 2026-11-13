'use client';

import Link from 'next/link';
import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { defaultProfile, normalizeProfile, readProfile, safeReturnPath } from '@/lib/demo-profile.mjs';

type Profile = { nickname: string; avatar: string };
type Session = { profile: Profile; signIn: () => void; signOut: () => void; saveProfile: (profile: Profile) => void };
const Context = createContext<Session | null>(null);
const profileKey = 'finsentinel.demo.profile.v1';
const sessionKey = 'finsentinel.demo.session.v1';

export function DemoSession({ children }: { children: React.ReactNode }) {
  const [profile, setProfile] = useState<Profile>(defaultProfile);
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    try { setProfile(readProfile(localStorage.getItem(profileKey))); setSignedIn(sessionStorage.getItem(sessionKey) === '1'); } catch { /* Storage can be disabled; login explains the failure. */ }
    setReady(true);
    const sync = (event: StorageEvent) => { if (event.key === profileKey || event.key === null) { try { setProfile(readProfile(localStorage.getItem(profileKey))); } catch { /* Keep the current profile. */ } } };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  useEffect(() => {
    if (ready && !signedIn && pathname !== '/login') router.replace(`/login?next=${encodeURIComponent(safeReturnPath(pathname))}`);
  }, [ready, signedIn, pathname, router]);
  const session: Session = {
    profile,
    signIn() { sessionStorage.setItem(sessionKey, '1'); setSignedIn(true); },
    signOut() { try { sessionStorage.removeItem(sessionKey); } finally { setSignedIn(false); router.replace('/login'); } },
    saveProfile(value) { const next = normalizeProfile(value); localStorage.setItem(profileKey, JSON.stringify(next)); setProfile(next); },
  };
  return <Context.Provider value={session}>{!ready || (!signedIn && pathname !== '/login') ? <div className="session-loading" role="status">正在打开研究工作台…</div> : children}</Context.Provider>;
}

export function useDemoSession() {
  const session = useContext(Context);
  if (!session) throw new Error('DemoSession provider is required');
  return session;
}

export function UserAvatar({ profile }: { profile: Profile }) {
  return <span className="avatar user-avatar">{profile.avatar ? <img src={profile.avatar} alt="" /> : Array.from(profile.nickname)[0]}</span>;
}

export function ProfileLink({ compact = false }: { compact?: boolean }) {
  const { profile } = useDemoSession();
  return <Link href="/settings" className={compact ? 'profile-shortcut' : 'profile profile-link'} aria-label={`${profile.nickname}，个人设置`}><UserAvatar profile={profile} />{!compact && <><span>{profile.nickname}<small>个人设置 · 演示账户</small></span><span aria-hidden="true">⚙</span></>}</Link>;
}

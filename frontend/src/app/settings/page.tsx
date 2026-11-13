'use client';

import Link from 'next/link';
import { FormEvent, useRef, useState } from 'react';
import { ProfileLink, UserAvatar, useDemoSession } from '@/components/demo-session';

async function avatarFromFile(file: File): Promise<string> {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('请选择 JPG、PNG 或 WebP 图片。');
  if (file.size > 2 * 1024 * 1024) throw new Error('图片不能超过 2 MB。');
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => { img.onload = () => resolve(); img.onerror = () => reject(new Error('图片无法读取，请换一张图片。')); img.src = url; });
    const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 256;
    const ctx = canvas.getContext('2d'); if (!ctx) throw new Error('当前浏览器无法处理头像。');
    const size = Math.min(img.naturalWidth, img.naturalHeight);
    if (!size) throw new Error('图片尺寸无效。');
    ctx.fillStyle = '#fdfcf9'; ctx.fillRect(0, 0, 256, 256);
    ctx.drawImage(img, (img.naturalWidth - size) / 2, (img.naturalHeight - size) / 2, size, size, 0, 0, 256, 256);
    const data = canvas.toDataURL('image/jpeg', .85);
    if (data.length > 200000) throw new Error('图片处理失败，请选择更简单的头像。');
    return data;
  } finally { URL.revokeObjectURL(url); }
}

export default function SettingsPage() {
  const { profile, saveProfile, signOut } = useDemoSession();
  const [nickname, setNickname] = useState(profile.nickname);
  const [avatar, setAvatar] = useState(profile.avatar);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadId = useRef(0);
  async function upload(file?: File) {
    if (!file) return;
    const id = ++uploadId.current; setBusy(true); setError(''); setMessage('');
    try { const data = await avatarFromFile(file); if (id === uploadId.current) setAvatar(data); }
    catch (cause) { if (id === uploadId.current) setError(cause instanceof Error ? cause.message : '图片处理失败。'); }
    finally { if (id === uploadId.current) setBusy(false); if (fileInput.current) fileInput.current.value = ''; }
  }
  function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('');
    if (!nickname.trim() || Array.from(nickname.trim()).length > 24) { setError('昵称需要 1–24 个字符。'); return; }
    try { saveProfile({ nickname, avatar }); setNickname(nickname.trim()); setMessage('个人资料已保存。'); }
    catch { setError('保存失败，浏览器存储可能已满或被禁用；原资料未更改。'); }
  }
  return <div className="shell"><aside className="sidebar"><Link className="brand" href="/"><span className="brand-mark">F</span><span>FinSentinel<small>金融证据链研判平台</small></span></Link><div className="nav-caption">研究工作台</div><nav><Link className="nav-item" href="/">◈ 监控总览</Link><Link className="nav-item" href="/compare">⇄ 证据比较</Link><Link className="nav-item active" href="/settings" aria-current="page">⚙ 个人设置</Link></nav><div className="sidebar-bottom"><ProfileLink /></div></aside><main className="main"><header className="topbar"><div className="breadcrumb"><Link href="/">研究工作台</Link><span>/</span><strong>个人设置</strong></div><ProfileLink compact /></header><div className="content settings-content"><div className="page-heading"><div><h1>个人设置</h1><p>设置你在研究工作台中的昵称与头像。</p></div><span className="subtle-chip">本机演示账户</span></div><form className="panel settings-card" onSubmit={submit}><h2>个人资料</h2><div className="avatar-editor"><UserAvatar profile={{ nickname: nickname.trim() || '研究员', avatar }} /><div className="avatar-actions"><button className="secondary-button" type="button" disabled={busy} onClick={() => fileInput.current?.click()}>{busy ? '正在处理…' : '上传头像'}</button><button className="secondary-button" type="button" disabled={busy || !avatar} onClick={() => { setAvatar(''); setMessage(''); }}>恢复默认</button><input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" hidden aria-label="选择头像图片" onChange={e => upload(e.target.files?.[0])} /><p>JPG、PNG、WebP，最大 2 MB，自动居中裁剪。</p></div></div><label htmlFor="profile-nickname">昵称</label><input id="profile-nickname" value={nickname} maxLength={48} required onChange={e => { setNickname(e.target.value); setMessage(''); }} aria-describedby="nickname-help" /><p id="nickname-help" className="field-hint">1–24 个字符，保存后同步更新侧栏与顶部头像。</p>{error && <p className="error form-message" role="alert">{error}</p>}<p className="save-message" role="status">{message}</p><div className="settings-footer"><span>资料仅保存在当前浏览器，不上传服务器。</span><button type="submit" className="primary-button" disabled={busy}>保存修改</button></div></form><section className="panel settings-card session-card"><div><h2>演示会话</h2><p>退出后回到登录页；已保存的昵称和头像会保留。</p></div><button type="button" className="secondary-button" onClick={signOut}>退出登录</button></section></div></main></div>;
}

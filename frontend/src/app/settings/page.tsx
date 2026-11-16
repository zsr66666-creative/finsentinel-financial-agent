'use client';

import Link from 'next/link';
import { PortalShell } from '@/components/portal-shell';
import { FormEvent, useRef, useState } from 'react';
import { UserAvatar, useSession } from '@/components/demo-session';

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
  const { profile, user, saveProfile, signOut, changePassword } = useSession();
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
  async function submit(event: FormEvent) {
    event.preventDefault(); if(busy)return;setError(''); setMessage('');
    if (!nickname.trim() || Array.from(nickname.trim()).length > 24) { setError('昵称需要 1–24 个字符。'); return; }
    setBusy(true);
    try { await saveProfile({ nickname, avatar }); setNickname(nickname.trim()); setMessage('个人资料已保存。'); }
    catch (cause) { setError(cause instanceof Error?cause.message:'保存失败，请重试。'); }finally{setBusy(false);}
  }
  return <PortalShell title="个人设置"><div className="content settings-content"><div className="page-heading"><div><h1>个人设置</h1><p>设置你在研究工作台中的昵称与头像。</p></div><span className="subtle-chip">{user?.username}</span></div>{error&&<p className="error form-message" role="alert">{error}</p>}{user?.must_change_password?<p className="review-callout" role="alert">首次登录或密码已重置，请先修改临时密码。</p>:<form className="panel settings-card" onSubmit={submit}><h2>个人资料</h2><div className="avatar-editor"><UserAvatar profile={{ nickname: nickname.trim() || '研究员', avatar }} /><div className="avatar-actions"><button className="secondary-button" type="button" disabled={busy} onClick={() => fileInput.current?.click()}>{busy ? '正在处理…' : '上传头像'}</button><button className="secondary-button" type="button" disabled={busy || !avatar} onClick={() => { setAvatar(''); setMessage(''); }}>恢复默认</button><input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" hidden aria-label="选择头像图片" onChange={e => upload(e.target.files?.[0])} /><p>JPG、PNG、WebP，最大 2 MB，自动居中裁剪。</p></div></div><label htmlFor="profile-nickname">昵称</label><input id="profile-nickname" value={nickname} maxLength={48} required onChange={e => { setNickname(e.target.value); setMessage(''); }} aria-describedby="nickname-help" /><p id="nickname-help" className="field-hint">1–24 个字符，保存后同步更新侧栏与顶部头像。</p><p className="save-message" role="status">{message}</p><div className="settings-footer"><span>资料保存在服务器，跨浏览器同步。</span><button type="submit" className="primary-button" disabled={busy}>保存修改</button></div></form>}<PasswordForm onChange={changePassword}/>{user?.role==='admin'&&!user.must_change_password&&<Link className="secondary-button" href="/admin/users">管理用户账号</Link>}<section className="panel settings-card session-card"><div><h2>账号会话</h2><p>退出后撤销当前会话，返回登录页。</p></div><button type="button" className="secondary-button" onClick={()=>{void signOut().catch(cause=>setError(cause.message));}}>退出登录</button></section></div></PortalShell>;
}

function PasswordForm({onChange}:{onChange:(current:string,next:string)=>Promise<void>}){
 const [current,setCurrent]=useState('');const [next,setNext]=useState('');const [confirm,setConfirm]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 async function submit(e:FormEvent){e.preventDefault();if(next!==confirm){setError('两次新密码不一致。');return;}setBusy(true);setError('');try{await onChange(current,next);setCurrent('');setNext('');setConfirm('');}catch(cause){setError(cause instanceof Error?cause.message:'修改失败。');}finally{setBusy(false);}}
 return <form className="panel settings-card" onSubmit={submit}><h2>修改密码</h2><p>新密码 12–128 个字符。修改成功后需重新登录。</p><label>当前密码<input type="password" autoComplete="current-password" value={current} onChange={e=>setCurrent(e.target.value)} required maxLength={128}/></label><label>新密码<input type="password" autoComplete="new-password" value={next} onChange={e=>setNext(e.target.value)} required minLength={12} maxLength={128}/></label><label>确认新密码<input type="password" autoComplete="new-password" value={confirm} onChange={e=>setConfirm(e.target.value)} required minLength={12} maxLength={128}/></label>{error&&<p role="alert" className="error">{error}</p>}<button className="primary-button" disabled={busy}>{busy?'修改中…':'修改密码并重新登录'}</button></form>;
}

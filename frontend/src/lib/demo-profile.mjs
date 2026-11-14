export const defaultProfile = { nickname: '研究员', avatar: '' };
export function normalizeProfile(value) {
  const nickname = typeof value?.nickname === 'string' ? value.nickname.trim() : '';
  const avatar = typeof value?.avatar === 'string' && value.avatar.length <= 200000 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(value.avatar) ? value.avatar : '';
  return { nickname: nickname && Array.from(nickname).length <= 24 ? nickname : defaultProfile.nickname, avatar };
}
export function readProfile(raw) {
  try { return normalizeProfile(JSON.parse(raw)); } catch { return { ...defaultProfile }; }
}
export function safeReturnPath(path) {
  return ['/', '/compare', '/settings'].includes(path) || (typeof path === 'string' && /^\/companies\/[A-Za-z0-9_-]{1,64}$/.test(path)) ? path : '/';
}
export function demoCredentialsValid(account, password) {
  return typeof account === 'string' && !!account.trim() && typeof password === 'string' && !!password.trim();
}

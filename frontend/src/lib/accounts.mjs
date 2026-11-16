let csrfToken = '';
export function setCsrfToken(value) { csrfToken = value; }
export async function authFetch(path, init = {}) {
 if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || /[\u0000-\u0020\u007f\\]/.test(path)) throw new Error('仅允许同源请求。');
 const headers = new Headers(init.headers);
 if (!['GET','HEAD','OPTIONS'].includes((init.method || 'GET').toUpperCase()) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
 const response = await fetch(path, {...init, headers, credentials:'same-origin', cache:'no-store'});
 if (response.status === 401 && !path.startsWith('/api/v1/auth/login') && typeof window !== 'undefined') window.dispatchEvent(new Event('finsentinel-session-expired'));
 return response;
}
export function secureAccountOrigin(location) { return location.protocol === 'https:' || (location.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(location.hostname)); }
export async function accountRequest(path, body) {
 if (typeof window !== 'undefined' && !secureAccountOrigin(window.location)) throw new Error('请使用 HTTPS 安全连接后登录或修改账号。');
 const response = await authFetch('/api/v1/auth' + path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
 if (!response.ok) {
  const messages = {401:'账号或密码错误，或会话已失效。',403:'权限不足，或需要先修改临时密码。',409:'操作冲突，请刷新后重试；请检查用户名或最后一位管理员限制。',422:'输入格式不符合要求，请检查后重试。',429:'尝试过于频繁，请稍后重试。',503:'账号服务暂不可用，请稍后重试。'};
  const error = new Error(messages[response.status] || `请求失败（${response.status}）。`); error.status = response.status; throw error;
 }
 return response.status === 204 ? null : response.json();
}

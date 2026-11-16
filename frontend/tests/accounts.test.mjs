import test from 'node:test';
import assert from 'node:assert/strict';
import {authFetch, setCsrfToken, secureAccountOrigin, accountRequest} from '../src/lib/accounts.mjs';
test('same origin requests attach CSRF on writes only and never allow remote credentials',async()=>{
 const original=globalThis.fetch; const calls=[]; globalThis.fetch=async(...args)=>{calls.push(args);return {status:200};};
 try {setCsrfToken('session-csrf');await authFetch('/api/v1/auth/profile',{method:'POST'});await authFetch('/api/v1/auth/session');assert.equal(calls[0][1].headers.get('X-CSRF-Token'),'session-csrf');assert.equal(calls[1][1].headers.has('X-CSRF-Token'),false);assert.equal(calls[0][1].credentials,'same-origin');await assert.rejects(()=>authFetch('https://evil.test/api'));}finally{globalThis.fetch=original;setCsrfToken('');}
});

test('account credentials require HTTPS except explicit loopback development',()=>{
 for(const hostname of ['120.24.108.60','localhost.evil.test','example.com']) assert.equal(secureAccountOrigin({protocol:'http:',hostname}),false);
 for(const hostname of ['localhost','127.0.0.1','[::1]']) assert.equal(secureAccountOrigin({protocol:'http:',hostname}),true);
 assert.equal(secureAccountOrigin({protocol:'https:',hostname:'120.24.108.60'}),true);
});

test('reject malformed same-origin targets before fetch',async()=>{
 for(const path of ['//evil.test','/\\evil.test','/\n/evil.test','https://evil.test']) await assert.rejects(()=>authFetch(path));
});
test('account failures stay failures with status, 204 never invents a user',async()=>{
 const original=globalThis.fetch;
 try { for(const status of [401,403,503]){globalThis.fetch=async()=>({ok:false,status});await assert.rejects(()=>accountRequest('/login',{username:'user',password:'wrong'}),e=>e.status===status);}
 globalThis.fetch=async()=>({ok:true,status:204});assert.equal(await accountRequest('/logout',{}),null);
 }finally{globalThis.fetch=original;}
});
test('insecure public origin blocks sensitive request before sending body',async()=>{
 const originalFetch=globalThis.fetch;const originalWindow=globalThis.window;let sent=false;
 globalThis.window={location:{protocol:'http:',hostname:'120.24.108.60'}};globalThis.fetch=async()=>{sent=true;return {ok:true,status:204};};
 try{await assert.rejects(()=>accountRequest('/login',{password:'never-send-this'}),/HTTPS/);assert.equal(sent,false);}finally{globalThis.fetch=originalFetch;if(originalWindow===undefined)delete globalThis.window;else globalThis.window=originalWindow;}
});

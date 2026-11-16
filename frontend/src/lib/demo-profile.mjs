import { parseReaderQuery } from './reader.mjs';
export function safeReturnPath(path) {
  if (typeof path === 'string' && /^\/research-reports\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(path)) return path;
  if (typeof path === 'string' && path.startsWith('/reader?') && parseReaderQuery(new URLSearchParams(path.slice(8)))) return path;

  return ['/my-research', '/admin/operations', '/admin/users', '/', '/compare', '/settings', '/companies', '/reports', '/evidence', '/workbench', '/workbench/alerts', '/workbench/companies', '/workbench/review', '/workbench/evals', '/workbench/data'].includes(path) || (typeof path === 'string' && /^\/companies\/[A-Za-z0-9_-]{1,64}$/.test(path)) ? path : '/';
}

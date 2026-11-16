export function safeReturnPath(path) {
  return ['/admin/operations', '/admin/users', '/', '/compare', '/settings', '/companies', '/reports', '/evidence', '/workbench', '/workbench/alerts', '/workbench/companies', '/workbench/review', '/workbench/evals', '/workbench/data'].includes(path) || (typeof path === 'string' && /^\/companies\/[A-Za-z0-9_-]{1,64}$/.test(path)) ? path : '/';
}

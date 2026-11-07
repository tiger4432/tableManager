// A template's address pattern against a page address: «*» is any run of characters, the scheme is not compared.
const bare = (s) => String(s || '').replace(/^[a-z][a-z0-9+.-]*:\/\//i, '');

export function matches(pattern, href) {
  if (!pattern) return false;
  const re = new RegExp(`^${bare(pattern).split('*').map((p) => p.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*')}$`, 'i');
  return re.test(bare(href));
}

/** The pattern a new template starts with: this page's host and path, then «*». */
export const patternOf = (href) => { const u = new URL(href); return `${u.host}${u.pathname}*`; };

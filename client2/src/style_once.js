// A part's rules into a document, once (lead 11-07): the part carries its look and the page gathers nothing - the walk's
// parts, the image preview and the option list each call this with their own stamp. A document with nowhere to put a
// <style> (a headless stub) is left alone.

/**
 * @param {Document} doc
 * @param {string} stamp  the attribute that marks this part's <style>
 * @param {string} css
 * @returns {boolean} whether this call put it in (a second call is false)
 */
export function ensureStyle(doc, stamp, css) {
  const at = doc && typeof doc.createElement === 'function' && (doc.head || doc.documentElement);
  if (!at || typeof at.appendChild !== 'function' || (doc.querySelector && doc.querySelector(`style[${stamp}]`))) return false;
  const style = doc.createElement('style');
  style.setAttribute(stamp, '');
  style.textContent = css;
  at.appendChild(style);
  return true;
}

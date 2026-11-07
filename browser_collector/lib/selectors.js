// A picked element as a selector the template keeps: a list item's selector names it and its alike siblings (the classes
// most of them carry), any other element's names it alone under its base (the document, the item or the content area).

const NAME = /^[A-Za-z_-][\w-]*$/;
const esc = (s) => (globalThis.CSS && CSS.escape ? CSS.escape(s) : s);
const classes = (el) => [...el.classList].filter((c) => NAME.test(c));
const segment = (el, keep = classes(el)) => el.tagName.toLowerCase() + keep.map((c) => `.${esc(c)}`).join('');

/** `el` alone under `base` (null: the document) - the shortest path of tag.class steps that names only it. */
export function selectorFor(el, base = null) {
  if (el === base) return '';
  const root = base || el.ownerDocument;
  const steps = [];
  for (let n = el; n && n !== base && n.nodeType === 1; n = n.parentElement) {
    if (!base && n.id && NAME.test(n.id)) { steps.unshift(`#${esc(n.id)}`); return steps.join(' > '); }
    let step = segment(n);
    const parent = n.parentElement;
    if (parent && [...parent.children].filter((c) => c.matches(step)).length > 1) {
      step += `:nth-of-type(${[...parent.children].filter((c) => c.tagName === n.tagName).indexOf(n) + 1})`;
    }
    steps.unshift(step);
    const sel = (base ? ':scope ' : '') + steps.join(' > ');
    if (root.querySelectorAll(sel).length === 1) return sel;
  }
  return (base ? ':scope > ' : '') + steps.join(' > ');
}

/** The list item a click inside it means: from `el` up, the first element that repeats among its siblings (two or more
 *  of its tag sharing a class with it, or classless like it) - a click on a row's subject is the row. */
export function repeating(el, stop = null) {
  for (let n = el; n && n !== stop && n.parentElement && n.tagName !== 'BODY'; n = n.parentElement) {
    const mine = classes(n);
    const alike = [...n.parentElement.children].filter((c) => c.tagName === n.tagName
      && (mine.length ? mine.some((k) => c.classList.contains(k)) : classes(c).length === 0));
    if (alike.length >= 2) return n;
  }
  return el;
}

/** A list item: `el` and the siblings of its tag that share its classes, under `area` (null: the document) -> {selector, count}. */
export function itemSelector(el, area = null) {
  const parent = el.parentElement;
  const alike = [...parent.children].filter((c) => c.tagName === el.tagName);
  const common = classes(el).filter((c) => alike.filter((s) => s.classList.contains(c)).length > alike.length / 2);
  const step = segment(el, common);
  const selector = parent === area ? `:scope > ${step}` : `${selectorFor(parent, area)} > ${step}`;
  return { selector, count: (area || el.ownerDocument).querySelectorAll(selector).length };
}

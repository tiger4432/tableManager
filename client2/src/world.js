// THE LEDGER WORLDS A SCREEN READS (lead 64c380aeb). A screen holds its worlds in one seat and every request
// it sends goes through this, so no request carries a world of its own. None sends no argument, and a
// request naming no world reads the OPERATING world (server 6bfb6d4be) - so none follows whatever operates,
// and the default world is picked by its name like any other (lead 120450931 ①). A walk may read several
// worlds at once, one `world=` each in the order picked - the earlier pick wins a vocabulary tie (lead
// 99032248f); a screen that edits one world hands one name.

/** The worlds `value` names - a name, a list or nothing - in order, blank names dropped. */
export function worldList(value) {
  return (Array.isArray(value) ? value : [value])
    .filter((world) => typeof world === 'string' && world.trim()).map((world) => world.trim());
}

/** `fetchImpl` with `world=<name>` added to every URL for each world `worldOf()` names. */
export function withWorld(fetchImpl, worldOf) {
  return (url, init) => {
    const worlds = worldList(worldOf());
    if (!worlds.length) return fetchImpl(url, init);
    const text = String(url);
    const tail = worlds.map((world) => `world=${encodeURIComponent(world)}`).join('&');
    return fetchImpl(`${text}${text.includes('?') ? '&' : '?'}${tail}`, init);
  };
}

/** A page's address naming `worlds` instead of the ones it named - a page reads its worlds from its address. */
export function addressFor(href, worlds) {
  const page = new URL(href);
  page.searchParams.delete('world');
  for (const world of worldList(worlds)) page.searchParams.append('world', world);
  return page.toString();
}

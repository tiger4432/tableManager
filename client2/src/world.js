// THE LEDGER WORLD A SCREEN READS (lead 64c380aeb). A screen holds its world in one seat and every request
// it sends goes through this, so no request carries a world of its own. null sends no argument, and a
// request naming no world reads the OPERATING world (server 6bfb6d4be) - so null follows whatever operates,
// and the default world is picked by its name like any other (lead 120450931 ①).

/** `fetchImpl` with `world=<name>` added to every URL while `worldOf()` names a world. */
export function withWorld(fetchImpl, worldOf) {
  return (url, init) => {
    const world = worldOf();
    if (!world) return fetchImpl(url, init);
    const text = String(url);
    return fetchImpl(`${text}${text.includes('?') ? '&' : '?'}world=${encodeURIComponent(world)}`, init);
  };
}

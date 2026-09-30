// THE LEDGER WORLD A SCREEN READS (lead 64c380aeb). A screen holds its world in one seat and every request
// it sends goes through this, so no request carries a world of its own. The default (null) sends today's
// request, byte for byte - the default is no argument at all, not a name.

/** `fetchImpl` with `world=<name>` added to every URL while `worldOf()` names a branch. */
export function withWorld(fetchImpl, worldOf) {
  return (url, init) => {
    const world = worldOf();
    if (!world) return fetchImpl(url, init);
    const text = String(url);
    return fetchImpl(`${text}${text.includes('?') ? '&' : '?'}world=${encodeURIComponent(world)}`, init);
  };
}

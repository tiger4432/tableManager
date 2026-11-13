// The screen checker's pages keep every request's timing entry (lead 11-13 ㄱ): two checks («filter typed», «set applied»)
// ask performance.getEntriesByType('resource') whether a read went out, and the browser's default buffer holds 250 -
// full by «Filter, two values applied» at 1920x950 and 1920x1080 on the tab branch, where the read went out and the
// check said it did not (11-13 probe). Raised once at page start, never cleared: «since page start» stays true.
// 5000: the most entries one page held in a run is 323 (11-13, tab branch, index.html at six sizes), about fifteen times over.
export const RESOURCE_BUFFER = 5000;

/** The page-start script the checker adds to every page (Page.addScriptToEvaluateOnNewDocument). */
export function resourceBufferSource(size = RESOURCE_BUFFER) {
  return `try { performance.setResourceTimingBufferSize(${size}); } catch (e) {}`;
}

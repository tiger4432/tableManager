// Put into a tab on demand (background.js inject); a content script cannot be a module, so it imports the one that is.
// The last expression is the promise the injection waits for.
(async () => {
  if (!window.__collector) window.__collector = import(chrome.runtime.getURL('page/main.js'));
  await window.__collector;
  return true;
})();

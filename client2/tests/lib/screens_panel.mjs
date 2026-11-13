// The screen checker's one judgement «is this element, floating new after a header button is pressed, that button's
// panel» (lead 11-13 ㄱ3). The checker hands this function's text into the page, so it reads only the description given.
// An AG Grid overlay (.ag-overlay*: no rows, loading) is the grid redrawing, not a panel: a Refresh's redraw showed
// «No Rows To Show» for 250 ms and the checker called it Refresh's panel, 76 px under the button (11-13 probe).
export function opensAsPanel({ classes, width, height }) {
  if (classes.some((c) => c === 'ag-overlay' || c.startsWith('ag-overlay-'))) return false;
  return width > 40 && height > 20;
}

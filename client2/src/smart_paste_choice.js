// ═══════════════════════════════════════════════════════════════════════════════
// SMART PASTE — which clipboard format is sent (lead 8771e43ac 1, owner 「페이스트는 ㄱ으로해」).
//
// A table may declare its order (`table_config.<table>.smart_paste`, MIME as written, served by
// `/tables/<t>/schema`). The first of that order on the clipboard goes without asking. With no
// order, or none of it on the clipboard, it is as before: more than one format asks, one goes.
// Both readers (the paste event and navigator.clipboard.read) choose here. No format is named here.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * @param {string[]} textTypes the text-bearing formats on the clipboard, as the reader found them
 * @param {string[]|null} order the table's declared order, or null when it declares none
 * @param {(types: string[]) => Promise<string|null>} ask the dialog; resolves null when cancelled
 * @returns {Promise<{type: string|null, byOrder: boolean}>} `type` null = nothing to send
 */
export async function chooseClipboardType(textTypes, order, ask) {
  const types = Array.isArray(textTypes) ? textTypes : [];
  if (Array.isArray(order)) {
    const hit = order.find((type) => types.includes(type));
    if (hit) return { type: hit, byOrder: true };
  }
  if (types.length > 1) return { type: (await ask(types)) || null, byOrder: false };
  return { type: types[0] || null, byOrder: false };
}

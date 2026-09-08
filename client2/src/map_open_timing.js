// ═══════════════════════════════════════════════════════════════════════════════
// C-43 ① ③ — 맵 하나를 여는 데 «무엇이» 걸리나. 값으로.
//
// 🔴 THE COMPLAINT WAS 「사람들이 못 쓴다」 AND NOBODY HAD A NUMBER. The screen could open a
//    map, fail to open one, and say which — and could not say how long it took, how many calls
//    it made, or which call was the slow one. So every proposal about speed was a guess, and
//    the one measurement anybody had was a person's patience.
//
// 🔴 COUNTED AT THE DOOR, NOT AT THE CALL SITES. An instrument added to each known request
//    measures the requests somebody remembered; the opening path is spread over presets, paint
//    rules, a metadata probe, cells, overlays and virtual joins, and the ones worth finding are
//    exactly the ones nobody remembered. Wrapping the door counts what actually went out.
//
// 🔴 A REPEATED URL IS A FINDING, NOT A ROUNDING ERROR. Two identical calls in one open is the
//    screen asking the same question twice, and it has happened here before — two components
//    each resolving the same chip id. So the same URL twice is counted and NAMED.
//
// ⛔ 판단하지 않습니다. 「느리다」도 「빠르다」도 이 파일에 없습니다 — 문턱을 여기 적으면 그
//    문턱이 다음 사람의 «사실»이 됩니다. 수를 내고, 읽는 것은 사람이 합니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 시작 시각을 0 으로 두고 한 번의 열기를 기록합니다. `now` 는 주입 — 하니스가 시계를 쥡니다. */
export function createOpenTimer(now) {
  const clock = typeof now === 'function' ? now : (() => Date.now());
  const started = clock();
  const calls = [];
  let drawnAt = null;
  return {
    /** 요청 하나가 «끝났다». url 은 물어본 그대로 — 여기서 다듬으면 중복이 안 보입니다. */
    note(url, ms) {
      calls.push({ url: String(url == null ? '' : url), ms: Number(ms) || 0 });
    },
    /** 마지막 셀이 그려졌다. 「응답이 왔다」가 아니라 «보였다»가 사람이 기다린 것입니다. */
    drawn() { drawnAt = clock() - started; },
    summary() { return summarise(calls, drawnAt); },
  };
}

/**
 * 한 번의 열기가 남긴 것 — 수만.
 *
 * ⚠️ `drawnMs` 가 null 이면 「안 그려졌다」가 아니라 «아직 안 끝났다»입니다. 0 으로 채우면
 *    「즉시 그려졌다」가 되고, 그건 이 계기가 답할 수 있는 물음이 아닙니다.
 */
export function summarise(calls, drawnMs) {
  const list = Array.isArray(calls) ? calls : [];
  const seen = new Map();
  for (const call of list) seen.set(call.url, (seen.get(call.url) || 0) + 1);
  const duplicates = [...seen.entries()]
    .filter(([, times]) => times > 1)
    .map(([url, times]) => ({ url, times }))
    .sort((a, b) => b.times - a.times || (a.url < b.url ? -1 : 1));
  let slowest = null;
  for (const call of list) if (!slowest || call.ms > slowest.ms) slowest = call;
  return {
    requests: list.length,
    totalMs: list.reduce((sum, call) => sum + call.ms, 0),
    slowest: slowest ? { url: slowest.url, ms: slowest.ms } : null,
    drawnMs: typeof drawnMs === 'number' ? drawnMs : null,
    duplicates,
  };
}

/** 정수 ms. 소수점은 사람이 안 읽고, 0.1ms 를 구별해야 하는 물음이 아닙니다. */
const ms = (value) => `${Math.round(value)} ms`;

/**
 * 화면 한 줄 — «값만».
 *
 * ⛔ 문장이 아닙니다. 「7번 요청했고 가장 느린 것은…」이라고 쓰면 그 줄은 읽히지 않고,
 *    이 화면이 이미 한 번 걷어낸 부류입니다.
 * ⚠️ 안 잰 것은 «안 씁니다» — 그리기 전이면 그 조각이 없습니다. 「0 ms」로 채우면 즉시
 *    그려졌다는 «거짓»이 됩니다.
 */
export function timingText(summary) {
  if (!summary || typeof summary !== 'object') return '';
  const parts = [`요청 ${summary.requests}`];
  if (summary.slowest) parts.push(`최장 ${ms(summary.slowest.ms)}`);
  if (summary.drawnMs !== null && summary.drawnMs !== undefined) {
    parts.push(`그리기 ${ms(summary.drawnMs)}`);
  }
  if (summary.duplicates && summary.duplicates.length) {
    const repeats = summary.duplicates.reduce((sum, d) => sum + (d.times - 1), 0);
    parts.push(`중복 ${repeats}`);
  }
  return parts.join(' · ');
}

/** 중복 URL 을 «이름 대어» — 툴팁 한 칸. 줄에는 수만, 이름은 여기. */
export function duplicateTitle(summary) {
  const dupes = summary && Array.isArray(summary.duplicates) ? summary.duplicates : [];
  return dupes.map((d) => `${d.times}× ${d.url}`).join('\n');
}

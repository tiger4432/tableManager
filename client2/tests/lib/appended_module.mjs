// APPENDED MODULE — 「원본 «전문» + 접근자」 사본을 만들어 import 합니다.
//
// 🔴 이것이 이 축의 «근원 템플릿»입니다. 지금 하니스 여럿이 대상 파일을 «텍스트로 읽어»
//    함수 본문을 잘라내고 vm 에 넣습니다. 소유자 상설(2026-09-02)이 그것을 금지했고,
//    이유는 그것이 «동작»이 아니라 «글자 모양»을 재기 때문입니다 —
//      import 를 하나 더하면      잘라낸 조각이 그 함수를 못 찾아 던집니다
//      const 를 하나 더하면       vm 에서 const 는 컨텍스트의 속성이 안 됩니다
//      함수가 헬퍼를 부르게 바뀌면  그 헬퍼가 「뽑을 목록」에 없어 던집니다
//    전부 «코드가 맞는데» 빨개집니다. 그리고 반대도 참입니다 — 틀렸는데 초록일 수 있습니다.
//
// ⚠️ 그래서 CLAUDE.md 가 허용한 «다리»가 덧붙이기입니다: 잘라내는 양이 «0» 이라
//    금지의 사유가 하나도 남지 않습니다 — import 도 const 도 헬퍼도 «파일 안에 그대로» 있습니다.
//
// 🔴 왜 그냥 import 하면 안 되나 (2026-09-05 실측):
//      `import('../src/map_editor.js')`  ->  «성공». 옛 사유(`import './tokens.css'`)는 사라졌습니다
//      그런데 `exported names = 0`       ->  밖에서 «잡을 이름»이 없습니다
//    ESM 네임스페이스는 봉인돼 있고 `export let` 도 밖에선 읽기 전용이라, 접근자를 «붙이는»
//    것 말고는 모듈 내부를 재는 길이 없습니다.
//
// 🔴 퇴화 방지 단언이 «이 헬퍼 안»에 있습니다. 밖에 두면 24 군데가 각자 만들고,
//    그러면 병이 이름만 바뀝니다. 사본이 «원본 바이트로 시작»하지 않으면 던집니다.
//
// ⚠️ 도착지가 아닙니다. 도착지는 「재려는 로직을 import 되는 모듈로 뺀다」이고, 이건 그
//    대공사를 오늘 안 하기 위한 다리입니다. 다리를 영구 건물로 읽지 마십시오.

import { readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, basename, join } from 'node:path';

let seq = 0;

/**
 * 원본 «전문» 뒤에 접근자를 붙인 사본을 만들고 import 합니다.
 *
 * 🔴 사본은 원본 «옆»에 놓입니다 — 상대 import(`./config.js` 등)가 그대로 풀려야 하기
 *    때문입니다. 다른 곳에 두면 그 import 들이 죽고, 그러면 우리가 고치려던 그 병
 *    (「코드가 맞는데 빨개진다」)을 다시 만듭니다.
 *
 * @param {URL|string} sourceUrl  대상 모듈의 URL (보통 `new URL('../src/x.js', import.meta.url)`)
 * @param {string} accessors      뒤에 붙일 소스. `export` 문을 여기 씁니다
 * @returns {Promise<object>}     import 된 네임스페이스
 */
export async function importWithAccessors(sourceUrl, accessors) {
  const srcPath = typeof sourceUrl === 'string' ? sourceUrl : fileURLToPath(sourceUrl);
  const original = readFileSync(srcPath, 'utf8');
  const copyPath = join(dirname(srcPath),
    `.appended-${basename(srcPath, '.js')}-${process.pid}-${seq++}.mjs`);
  const body = original + '\n' + accessors;

  // 🔴 THE ASSERTION THAT KEEPS THIS FROM BECOMING SLICING AGAIN. Nothing is removed, so
  //    the copy must start with the original byte for byte. If a future edit "just tidies
  //    one import away", this throws instead of quietly measuring a different program.
  if (!body.startsWith(original)) {
    throw new Error('appended copy does not start with the original bytes — '
      + 'something was removed, which makes this slicing again');
  }
  writeFileSync(copyPath, body, 'utf8');
  try {
    return await import(pathToFileURL(copyPath).href);
  } finally {
    // ⚠️ 반드시 지웁니다. 남으면 `src/` 에 추적 안 되는 파일이 생기고, 다음 사람의
    //    `git status` 에 «남의 것»처럼 보입니다.
    try { unlinkSync(copyPath); } catch { /* already gone */ }
  }
}

/** 사본이 원본으로 시작한다는 그 규칙 자체를 하니스가 «재 볼» 수 있게 노출합니다. */
export function startsWithOriginal(original, appended) {
  return typeof original === 'string' && typeof appended === 'string'
    && appended.startsWith(original);
}

/**
 * 원본에 «변이 하나»를 넣은 사본을 만들어 import 합니다. 변이 하니스 전용입니다.
 *
 * 🔴 왜 별도 함수인가: `importWithAccessors` 는 「사본이 원본 바이트로 «시작»한다」를 단언합니다.
 *    그것이 덧붙이기가 잘라쓰기로 퇴화하지 않게 막는 장치인데, «변이»는 정의상 바이트를
 *    바꿉니다. 그래서 같은 함수에 넣을 수 없고, 대신 «다른 단언»이 자리를 지킵니다:
 *
 *      덧붙이기   사본이 원본으로 «시작»해야 한다        (아무것도 안 빠졌다)
 *      변이       사본이 원본과 «달라야» 한다            (변이가 «먹었다»)
 *
 * ⚠️ 이 단언이 없으면 「변이가 안 먹었는데 초록」이 되고, 그건 이 저장소가 겪은 부류입니다 —
 *    앵커가 낡아 안 맞으면 변이 하니스가 «조용히» 아무것도 안 재게 됩니다.
 *
 * 🔵 그리고 이건 잘라쓰기가 «아닙니다» — 잘라내는 것이 없습니다. 파일 전문이 그대로 있고
 *    한 자리만 바뀝니다. import·const·헬퍼가 전부 사본 안에 살아 있습니다.
 *
 * @param {URL|string} sourceUrl  대상 모듈
 * @param {(src: string) => string} mutate  원본 소스를 받아 «바뀐» 소스를 돌려줍니다
 * @returns {Promise<object>} import 된 네임스페이스
 */
export async function importMutated(sourceUrl, mutate) {
  const srcPath = typeof sourceUrl === 'string' ? sourceUrl : fileURLToPath(sourceUrl);
  // 🔴 줄바꿈을 정규화합니다. 변이 앵커는 줄바꿈이 든 여러 줄 문자열인데 저장소는 CRLF 로
  //    체크아웃되므로, 정규화 없이는 «맞는 앵커»가 새 워크트리에서만 조용히 빗나갑니다
  //    (2026-07-30 실측: 변이 18 중 8 이 그렇게 안 먹은 채 초록이었습니다).
  const original = readFileSync(srcPath, 'utf8').replace(/\r\n/g, '\n');
  const body = mutate(original);
  if (typeof body !== 'string') {
    throw new Error('mutate() must return the mutated source as a string');
  }
  if (body === original) {
    throw new Error('the mutation changed nothing — its anchor no longer matches. '
      + 'A mutant that does not apply reads as a pass, which is worse than no harness.');
  }
  const copyPath = join(dirname(srcPath),
    `.appended-${basename(srcPath, '.js')}-${process.pid}-${seq++}.mjs`);
  writeFileSync(copyPath, body, 'utf8');
  try {
    return await import(pathToFileURL(copyPath).href);
  } finally {
    try { unlinkSync(copyPath); } catch { /* already gone */ }
  }
}

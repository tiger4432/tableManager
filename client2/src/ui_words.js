// UI WORDS — a word three or more files draw for the same fact, spelled once (총괄 dd00d6dad).
//
// 🔴 ONLY WHOLE WORDS. A counter or a sentence piece (「개」 · 「건」 · 「행」 · 「전」) is not a fact of its
//    own: English moves it, drops it or pluralises it per sentence, so each sentence is written whole
//    where it is drawn. Absence words («not asked» · «unknown») stay in `absent.js`, their seat.

export const LOADING = 'Loading…';
export const WALKING = 'Walking…';
export const SERVER_REFUSED = 'Server refused';
export const WAITING = 'Waiting';
export const FAILED = 'Failed';
export const REFUSED = 'Refused';
export const NONE = 'None';
export const NO_VALUE = 'No value';
export const CHOOSE = '— choose —';

/** The refusal three write paths (edit · paste · fill) give a value that is not a number. */
export function notANumber(column, value) {
  return `Column '${column}': '${value}' is not a number`;
}

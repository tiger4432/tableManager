// The ledger declaration window's sample (the owner's mockup's own data, task/design/LEDGER_DECLARATION_BAR.dc.html) - what
// the sample page draws and the side-by-side shots compare until implementer B's short form opens its doors. Example
// rows, not a box's declaration.

export const SAMPLE_RAW = Object.freeze({
  table: 'wafer_process_recipe',
  occurred_at: { column: 'eventtime', timezone: 'Asia/Seoul' },
  identity: 'row_id',
  attributes: { wafer: { lot: 'lot_id', step: 'step' } },
  sentences: [
    { sentence: 'wafer-processed-with-recipe', subject: { node: 'wafer', keys: { wafer: 'wafer_id' } }, predicate: 'processed_with',
      target: { node: 'recipe', keys: { recipe: 'recipe_id' } }, step: 'step', when: { column: 'mat_type', is: 'blank' } },
    { sentence: 'dtwafer-processed-with-recipe', subject: { node: 'dt_wafer', keys: { dt_wafer: 'wafer_id' } }, predicate: 'processed_with',
      target: { node: 'recipe', keys: { recipe: 'recipe_id' } }, when: { column: 'mat_type', equals: 'DT' } },
    { sentence: 'die-transfer', source: 'transfer_event, a key of four parts',
      subject: { node: 'die', keys: { mat_id: 'core_wafer_id', mat_type: { const: 'Wafer' }, x: 'c_wx', y: 'c_wy' } }, predicate: 'transferred_to',
      target: { node: 'die', keys: { mat_id: 'dt_job_id', mat_type: { const: 'DT' }, x: 'b_wx', y: 'b_wy' } } },
  ],
});

export const SAMPLE_VIEW = Object.freeze({
  kind: 'source', name: 'wafer_process_recipe', sourceId: 'wafer_process_recipe', open: 'sentences.0.subject.keys.wafer', picked: 0,
  active: true, draftAge: 'edited 2 min ago',
  catalog: { tables: { wafer_process_recipe: [
    { name: 'wafer_id', type: 'text' }, { name: 'lot_id', type: 'text' }, { name: 'recipe_id', type: 'text' },
    { name: 'step', type: 'text' }, { name: 'slot', type: 'number' }, { name: 'eventtime', type: 'datetime' }] } },
  entities: [{ type: 'wafer', keys: ['wafer'], attributes: ['lot', 'step'] }, { type: 'dt_wafer', keys: ['dt_wafer'] }, { type: 'recipe', keys: ['recipe'] },
    { type: 'die', keys: ['mat_id', 'mat_type', 'x', 'y'] }],
  predicates: [{ name: 'processed_with', qualifiers: ['step'] }, { name: 'transferred_to', qualifiers: [] }],
  sources: [{ key: 'source_plan|wafer_process_recipe', id: 'wafer_process_recipe' }, { key: 'source_plan|transfer_event', id: 'transfer_event' }],
  run: { rows: 3, edges: 3, refused: 1, refusals: ['row 1204: recipe_id is blank — no target'], lines: [
    { row: '1201', sentence: 'wafer-processed-with-recipe', subject: { node: 'wafer', key: 'SYN-BW-103-11' }, predicate: 'processed_with',
      target: { node: 'recipe', key: 'RCP-BOND-07' }, with: { name: 'step', value: 'BOND' }, at: '2026-10-14 09:12:00' },
    { row: '1202', sentence: 'wafer-processed-with-recipe', subject: { node: 'wafer', key: 'SYN-BW-103-12' }, predicate: 'processed_with',
      target: { node: 'recipe', key: 'RCP-BOND-07' }, with: { name: 'step', value: 'BOND' }, at: '2026-10-14 09:14:30' },
    { row: '1203', sentence: 'dtwafer-processed-with-recipe', subject: { node: 'dt_wafer', key: 'DT-0412' }, predicate: 'processed_with',
      target: { node: 'recipe', key: 'RCP-DT-02' }, with: null, at: '2026-10-14 09:20:05' }] },
  cost: { before: 'this source today: ', strong: 'same as before', after: ' — no re-translate' },
});

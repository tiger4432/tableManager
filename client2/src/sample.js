// SAMPLE PAGE — every base element on one page (lead de64fb0f9). The looks are base.css; this
// file only loads the two layers and flips the theme, so both halves of the tokens can be seen.
import './tokens.css';
import './base.css';
// The Spotfire standard's parts (ui-design-system §9), drawn on this page too.
import './spotfire.css';
// The ledger declaration window, drawn by its module on the mockup's data.
import './ledger_declaration_bar.css';
import { renderDeclarationBar } from './ledger_declaration_bar.js';
import { SAMPLE_RAW, SAMPLE_VIEW } from './ledger_declaration_sample.js';
// The declaration form's tree (form D), read-only: names three levels deep, the longest 40 letters.
import './ontology_explorer.css';
import { readContext, renderSkeletonForm } from './ontology_explorer_view.js';

const root = document.documentElement;
const button = document.getElementById('sample-theme');
const draw = () => {
  const dark = root.dataset.theme === 'dark';
  button.textContent = dark ? 'Light theme' : 'Dark theme';
};
button.addEventListener('click', () => {
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  draw();
});
if (!root.dataset.theme) root.dataset.theme = 'light';
draw();
const formMount = document.getElementById('sample-decl-form');
if (formMount) {
  const leaf = { kind: 'leaf', hint: 'free' };
  const skeleton = { kind: 'record', fields: [
    { key: 'name', required: true, node: leaf },
    { key: 'read', required: true, node: { kind: 'record', fields: [
      { key: 'table', required: true, node: leaf },
      { key: 'columns', required: false, node: { kind: 'map', keyed_by: 'index', member: 'column', of: leaf } },
      { key: 'time', required: false, node: { kind: 'record', fields: [
        { key: 'column', required: true, node: leaf },
        { key: 'a_forty_letter_name_of_a_declared_column', required: false, node: leaf }] } }] } },
    { key: 'limits', required: false, node: { kind: 'record', fields: [
      { key: 'group_by', required: false, node: leaf }, { key: 'unit', required: false, node: leaf }] } }] };
  // A list of words long enough to wrap (a chip row two lines high), and a block left folded (its summary).
  const columns = ['lot_id', 'wafer_id', 'slot', 'die_x', 'die_y', 'bin', 'soft_bin', 'test_program', 'tester', 'probe_card',
    'operator', 'started_at', 'ended_at', 'site', 'temperature', 'retest', 'yield', 'remark'];
  const value = { name: 'lot_master', read: { table: 'lot_master', columns, time: { column: 'observed_at', a_forty_letter_name_of_a_declared_column: 'Asia/Seoul' } },
    limits: { group_by: 'lot_id', unit: 'lot' } };
  const tree = renderSkeletonForm(readContext({}, { read: true, 'read.time': true, limits: false }), skeleton, '', value, 0, 'lot_master');
  formMount.replaceChildren(Object.assign(document.createElement('div'), { className: 'oe-skeleton-form' }));
  formMount.firstChild.append(tree);
}
const declMount = document.getElementById('sample-decl-bar');
// A chip pressed opens its list (the explorer's decl-open, here on the sample's own data); the page opens shut.
let declOpen = null;
const drawDecl = () => declMount.replaceChildren(renderDeclarationBar(document, SAMPLE_RAW, { ...SAMPLE_VIEW, open: declOpen }));
if (declMount) {
  drawDecl();
  declMount.addEventListener('click', (event) => {
    const chip = event.target.closest('[data-action="decl-open"]');
    if (!chip) return;
    declOpen = declOpen === chip.dataset.path ? null : chip.dataset.path;
    drawDecl();
  });
}

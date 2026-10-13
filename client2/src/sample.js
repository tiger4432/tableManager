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
const declMount = document.getElementById('sample-decl-bar');
if (declMount) declMount.replaceChildren(renderDeclarationBar(document, SAMPLE_RAW, SAMPLE_VIEW));

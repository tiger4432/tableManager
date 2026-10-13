// SAMPLE PAGE — every base element on one page (lead de64fb0f9). The looks are base.css; this
// file only loads the two layers and flips the theme, so both halves of the tokens can be seen.
import './tokens.css';
import './base.css';
// The Spotfire standard's parts (ui-design-system §9), drawn on this page too.
import './spotfire.css';

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

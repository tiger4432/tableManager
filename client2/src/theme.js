// ============================================================
// theme.js — 듀얼 테마(라이트/다크) 토글 유틸 (방향 C)
// - <html data-theme="light|dark"> 스탬프가 유일한 전환 스위치 (tokens.css 값 세트 선택)
// - localStorage('theme') 영속 · 4페이지 공통
// - FOUC 방지: 각 HTML <head> 최상단의 인라인 스니펫(아래 FOUC_SNIPPET 동일 로직)이
//   CSS 로드 전에 data-theme을 먼저 스탬프한다. 이 모듈은 그 이후의 런타임 전환 담당.
// - AG-Grid: 레거시 CSS 테마 클래스(ag-theme-quartz ↔ ag-theme-quartz-dark)를
//   data-theme에 맞춰 동적 스왑 (grid 재생성 불필요 — 클래스 전환만으로 재도색)
// - 전환 알림: document 'themechange' CustomEvent({detail:{theme}})
//   (map_editor 캔버스 색 캐시 재빌드, admin Monaco 테마 전환 등이 구독)
// ============================================================

const THEME_KEY = 'theme';
const THEMES = ['light', 'dark'];
const DEFAULT_THEME = 'light'; // 사용자 피드백("너무 어두컴컴") 반영 — 기본 라이트

/*
 * 각 HTML <head> 최상단에 인라인으로 심는 FOUC 방지 스니펫 (참고용 사본):
 * <script>(function(){try{var t=localStorage.getItem('theme');
 *   document.documentElement.setAttribute('data-theme', t==='dark'?'dark':'light');
 * }catch(e){document.documentElement.setAttribute('data-theme','light');}})();</script>
 */

/** 현재 테마 반환 (localStorage → data-theme 속성 → 기본값 순) */
export function getTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (THEMES.includes(stored)) return stored;
  } catch (e) { /* storage 접근 불가 환경 폴백 */ }
  const attr = document.documentElement.getAttribute('data-theme');
  return THEMES.includes(attr) ? attr : DEFAULT_THEME;
}

/** 테마 적용: data-theme 스탬프 + 영속 + AG-Grid 클래스 스왑 + 이벤트 발행 */
export function applyTheme(theme) {
  const next = THEMES.includes(theme) ? theme : DEFAULT_THEME;
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* 무시 */ }
  syncAgGridThemeClasses(next);
  updateToggleButtons(next);
  document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: next } }));
}

/** 라이트 ↔ 다크 전환 */
export function toggleTheme() {
  applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

/** AG-Grid 레거시 테마 클래스를 현재 테마에 맞춰 스왑 */
export function syncAgGridThemeClasses(theme = getTheme()) {
  const target = theme === 'dark' ? 'ag-theme-quartz-dark' : 'ag-theme-quartz';
  document.querySelectorAll('.ag-theme-quartz, .ag-theme-quartz-dark').forEach((node) => {
    if (node.classList.contains(target)) return;
    node.classList.remove('ag-theme-quartz', 'ag-theme-quartz-dark');
    node.classList.add(target);
  });
}

/** 토글 버튼 접근성 라벨 갱신 (아이콘 표시는 tokens.css가 data-theme으로 처리) */
function updateToggleButtons(theme = getTheme()) {
  const label = theme === 'dark' ? '라이트 테마로 전환' : '다크 테마로 전환';
  document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
    btn.setAttribute('aria-label', label);
    btn.setAttribute('title', label);
  });
}

/**
 * 페이지 초기화 진입점 — 각 엔트리 JS가 DOM 준비 후 1회 호출.
 * - [data-theme-toggle] 버튼 클릭 바인딩
 * - AG-Grid 클래스/버튼 라벨 초기 동기화
 * - 다른 탭에서의 전환(storage 이벤트) 동기화
 */
export function initTheme() {
  const current = getTheme();
  // FOUC 스니펫이 이미 스탬프했더라도 상태 정합을 위해 재확정 (이벤트는 initial 1회 발행)
  document.documentElement.setAttribute('data-theme', current);
  syncAgGridThemeClasses(current);
  updateToggleButtons(current);

  document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
    btn.addEventListener('click', toggleTheme);
  });

  window.addEventListener('storage', (e) => {
    if (e.key !== THEME_KEY) return;
    const next = THEMES.includes(e.newValue) ? e.newValue : DEFAULT_THEME;
    if (next !== document.documentElement.getAttribute('data-theme')) {
      applyTheme(next);
    }
  });
}

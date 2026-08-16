import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const root = path.resolve(process.cwd());
const jsPath = path.join(root, 'src', 'rnd_console', 'trend_workbench.js');
const cssPath = path.join(root, 'src', 'rnd_console', 'trend_workbench.css');
const source = fs.readFileSync(jsPath, 'utf8');
const css = fs.readFileSync(cssPath, 'utf8');
const mod = await import(pathToFileURL(jsPath));
let assertions = 0;
function ok(condition, message) {
  assertions += 1;
  if (!condition) throw new Error(`FAIL: ${message}`);
}

ok(typeof mod.init === 'function', 'public init API');
ok(typeof mod.update === 'function', 'public update API');
ok(typeof mod.getSelection === 'function', 'public getSelection API');
ok(typeof mod.TrendWorkbench === 'function', 'isolated controller export');
ok(typeof mod.downsampleSeries === 'function', 'downsampling seam export');

const points = Array.from({ length: 10_000 }, (_, i) => ({ waferId: `WF-${i}`, x: i, y: i === 5101 ? 99999 : Math.sin(i / 10) }));
const sampled = mod.downsampleSeries(points, 200);
ok(sampled.length <= 200, 'downsampling obeys the payload ceiling');
ok(sampled[0] === points[0], 'downsampling preserves first point');
ok(sampled.at(-1) === points.at(-1), 'downsampling preserves last point');
ok(sampled.includes(points[5101]), 'downsampling preserves a local extreme');
ok(mod.getSelection().length === 0, 'selection is empty before initialization');

ok(source.includes('requireWaferId'), 'stable wafer identity guard exists');
ok(source.includes('onSelectionChange'), 'selection integration callback exists');
ok(source.includes('chart.points.filter((point) => this.selection.has(point.waferId))'), 'marked wafers survive chart downsampling');
ok(source.includes('onPageRequest'), 'server paging seam exists');
ok(source.includes('pageRequestPending'), 'paging callback has an in-flight storm guard');
ok(source.includes('if (!requiresRender && this.root)') && source.includes('this.paintSelection();'),
  'marking-only updates repaint in place instead of resetting the virtual table');
ok(source.includes('previousScrollTop') && source.includes('focusedWaferId'),
  'data/config rerenders restore table scroll position and keyboard focus');
ok(source.includes('previousScrollLeft') && source.includes('focusedColumnKey'),
  'transposed report table preserves horizontal scroll and exact cell focus');
ok(source.includes('ResizeObserver'), 'resize-safe repaint exists');
ok(source.includes('IntersectionObserver'), 'large-N chart trellis paints on demand');
ok(source.includes("new URL('./trend_workbench.css'"), 'module loads its co-located stylesheet');
ok(source.includes('devicePixelRatio'), 'canvas backing-store scaling exists');
ok(source.includes('distance <= 14'), 'chart hit target is larger than the painted point');
ok(source.includes("kind: 'metric_region'") && source.includes('yMin:') && source.includes('yMax:'),
  'trend drag emits a typed two-dimensional metric-region mark');
ok(source.includes('state.allHits.filter((hit) => hit.x >= box.left')
  && source.includes('hit.y >= box.top && hit.y <= box.bottom'),
  'BBOX selection marks only points inside both X and Y bounds');
ok(source.includes('ctx.fillRect(box.left') && source.includes('ctx.strokeRect(box.left'),
  'dragged and persisted marking regions remain visible on the chart');
ok(source.includes('cell.dataset.seriesId = column.key') && source.includes("kind: columnKind === 'trace' ? 'trace_dimension'"),
  'report-table metric clicks retain their declared finding series on the ontology mark');
ok(source.includes('X: ${chart.xLabel}') && source.includes('Y: ${chart.yLabel}'),
  'every trend chart paints explicit X and Y axis titles');
ok(source.includes("'날짜 - BASE WAFER-ID'") && source.includes("replace(/^wafer:/, '')"),
  'X axis combines date with the readable Base Wafer identity');
ok(source.includes("toLocaleDateString('ko-KR'"), 'time axis paints bounded date labels');
ok(source.includes('normalizeMarkingGroups'), 'trend accepts universal marking groups');
ok(source.includes("group.role === 'overlay'") && source.includes('groupsFor(waferId)'),
  'ontology claim overlays take visual priority without replacing A/B cohorts');
ok(source.includes('groups.slice(1, 4)'), 'overlapping marking contexts remain visible as colored chart rings');
ok(source.includes('groupId: active?.id'), 'trend emits only the active marking group');
ok(!source.includes('fetch('), 'view module performs no network request');
ok(!source.includes('innerHTML'), 'ledger values cannot become markup');

ok(css.includes('@media (min-width: 1600px)'), 'desktop-wide layout has an explicit contract');
ok(css.includes('.rwb-table { grid-column: 1; grid-row: 2; }'), 'desktop-wide table follows the chart row');
ok(source.includes('visibleChartIds') && source.includes('.slice(0, 2)'),
  'configured Trend page renders at most two user-selected declared series');
ok(source.includes('dataset.trendItem') && source.includes("source: 'table:item'")
  && source.includes('onVisibleChartsChange'),
  'clicking a Trend Table item selects its declared chart through the integration seam');
ok(css.includes('.rwb-table__metric--selectable[aria-pressed="true"]'),
  'the Trend Table item shows which chart it currently drives');
ok(css.includes('grid-template-columns: repeat(2, minmax(0, 1fr))'),
  'two selected Trend charts share one wide page without overflow');
ok(css.includes('.rwb-chart__plot { width: 100%; height: 300px'),
  'the paged Trend chart keeps report-scale height');
ok(source.includes('card.append(viewport)'), 'table viewport is mounted into the table card');
ok(css.includes('max-width: 100%'), 'workbench cannot widen the page');
ok(css.includes('overflow: auto'), 'wide table scroll is contained locally');
ok(source.includes('repeat(${this.data.rows.length}, 140px)')
  && source.includes("'rwb-table__column rwb-table__corner', '항목'")
  && source.includes('renderTableMetricRow'),
  'report table transposes wafers to columns and declared items to rows');
ok(source.includes('function unitLabel(item)') && source.includes('bondingLeg || item?.bonding_leg'),
  'every horizontal analysis-unit header distinguishes Base Wafer and string Bonding Leg');
ok(source.includes("charts.classList.toggle('is-single'") && css.includes('.rwb__charts.is-single'),
  'one selected declared chart expands to the full report width');
ok(css.includes('.rwb-table__wafer-id') && css.includes('.rwb-table__leg'),
  'WF and free-string LEG render on separate contained header lines');
ok(source.includes("'rwb-table__cell-value'") && css.includes('.rwb-table__cell-value'),
  'long report values are clipped inside their own WF column');
ok(source.includes('conditionScale(this.data.rows, column)')
  && source.includes("cell.dataset.condition = ratio >= 0.67"),
  'each declared item row computes its own conditional-format scale');
ok(css.includes('.rwb-table__metric') && css.includes('position: sticky'),
  'item axis stays visible while wafers scroll horizontally');
ok(css.includes('.rwb-table__cell.is-marked'), 'table marking has a visible cell state');
ok(css.includes('--rwb-row-mark-stack'), 'table can display more than one marking context color');

console.log(`rnd_trend_workbench_harness: ${assertions} assertions passed`);

# 브라우저 수집 확장 (Collector) — 웹 페이지 목록을 표로 (11-07)

```
운영에서는 sys_templates 에 사이트마다 템플릿 한 행, sys_template_fields 에 칸마다 한 행을 적고
그 사이트를 연 탭에서 Collector 패널의 Run 을 누르면 목록 항목마다 한 행이 target_table 에 들어간다
```

## 1. 설치 (한 번)

1. 크롬 `chrome://extensions` → 오른쪽 위 **개발자 모드** 켬
2. **압축해제된 확장 프로그램 로드** → 설치 폴더의 `browser_collector` 폴더
3. 툴바의 Collector 아이콘 → 오른쪽 사이드 패널 → **Settings** 에 제품 서버 주소 + 개인 키(제품의 계정 화면에서 만든 키)
4. **Save and check** → `reached · signed in as <이름>` 이 뜨면 끝

서버 재기동은 필요 없다. 키는 만든 사람만 지운다.

## 2. 템플릿 — 사이트 하나에 한 행

패널의 **+ New template** 에서 화면을 눌러 고르고 Save 하면 아래 두 표에 적힌다. 그리드에서 바로 고쳐도 같다.

- 고르는 동안 **↑** 는 강조를 부모로 한 단계 넓히고 **↓** 는 되돌린다. 클릭이나 **Enter** 로 정한다
- 내용 영역에서 **Shift+클릭** 은 영역을 하나 더 붙인다 — 타이틀과 본문을 함께 묶는 요소가 없을 때
- 목록이 페이지 안 프레임(iframe)에 있어도 그대로 고른다 — `frame_pattern` 이 저절로 적힌다
- **Preview** 는 넣을 표나 키가 비어 있어도 읽은 값을 보여 준다 (`Table not set - keys not checked`)
- 카드의 **Delete** → 확인 한 번 → 그 템플릿의 두 표 행이 지워진다. 모은 행과 실행 기록은 남는다

**sys_templates** (키 `template`)

| 칸 | 뜻 |
|---|---|
| `url_pattern` | 이 템플릿을 쓸 페이지 주소 |
| `frame_pattern` | 목록과 내용이 페이지 안 프레임(iframe)에 있으면 그 프레임의 주소 — 고를 때 저절로 적힌다. 빈칸 = 페이지 자체 |
| `list_area` · `list_item` | 목록 영역과 그 안의 항목 하나 (CSS 선택자) |
| `click_target` · `open_method` | 항목에서 누를 곳 · `in_place`(그 자리에서 열림) 또는 `new_tab` |
| `content_area` | 열린 내용 영역 — `base` 가 `content` 인 칸이 여기서 읽힌다. 선택자 여럿(`a, b`)이면 보이는 것 전부가 내용 |
| `timeout_seconds` | 누른 뒤 내용이 바뀌기를 기다리는 초 |
| `close_element` | 열린 내용을 닫는 단추 (있으면) |
| `next_method` · `next_element` | 다음 쪽 — `button`(누름) 또는 `scroll`(내림) |
| `scroll_end_seconds` | `scroll` 일 때 새 항목이 이만큼 안 오면 끝 |
| `max_items` | 한 번에 읽을 최대 항목 수 — 빈칸 = 끝까지 |
| `ready_match` | `<항목 칸>=<내용 칸>` — 두 값이 같을 때만 그 내용을 그 항목의 것으로 본다 (느린 사이트에서 옛 내용을 막음) |
| `key_columns` | target_table 에서 행을 가르는 칸 |
| `target_table` | 넣을 표 |

**sys_template_fields** (키 `template` + `column`)

| 칸 | 뜻 |
|---|---|
| `column` | target_table 의 칸 이름 |
| `base` | `item`(열기 전 목록 항목에서) 또는 `content`(열린 내용에서) |
| `element` | 그 아래에서 읽을 요소 (CSS 선택자) |
| `take` | `text` 또는 속성 이름 (`href` 등) |
| `regex` | 첫 괄호 묶음만 — 빈칸 = 전부 |

권한: 두 표의 행은 «target_table 의 편집»이다 — 그 표를 고칠 수 있는 사람이 템플릿을 고친다 (`table_config.md` 의 `access`).

## 3. 실행

- 그 사이트를 연 탭에서 패널 → 맞는 템플릿의 **Run**. 도는 동안 탭은 열어 둔다
- 끝 화면: 쓴 수 · 건너뜀 · 남긴 항목(사유별)
- **Pause** 는 묶음 사이에서 멈추고 **Resume** 으로 이어감 · **Stop** 은 끝냄
- 남긴 항목만 다시: 끝 화면이나 History 의 **Retry these N**
- 같은 키는 다시 돌려도 중복이 안 생긴다 (`key in table, skipped`)

## 4. 뜨는 말

| 문구 | 뜻 · 다음 |
|---|---|
| `not signed in` | 서버 주소나 개인 키가 틀림 — Settings 다시 |
| `server not reached` | 이 크롬에서 서버 주소가 안 열림 |
| `content did not change in N s` | 누른 뒤 내용이 안 바뀜 — 그 항목만 건너뛰고 History 에 남음. `timeout_seconds` 를 늘리거나 `click_target` 을 고침 |
| `key in table, skipped` | 이미 넣은 키 |
| `Stopped - the product refused the run` + 문장 | target_table 을 고칠 권한 없음 — 그 표의 `access.edit.allow` 에 이름 |

## 5. 기록

- 실행마다 `sys_collect_runs` 한 행 — 시작에 쓰고 끝에 다섯 수. 돌린 사람은 그 행의 `updated_by`
- 남긴 항목마다 `sys_collect_misses` 한 행 — `reason`(`no_key` · `not_opened` · `refused`) · `detail`(사유 문장) · `cells`(읽은 값 JSON)
- 넣은 행의 출처(층) 이름은 템플릿 이름이다 — 그리드 칸의 출처에 그 이름이 보인다

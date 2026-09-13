# 인제션 파서 — 길이 «둘»입니다. 먼저 고르십시오

> **정본:** `server/parsers/pipeline_base.py` (109줄) @ `2a6adb50` ·
> `examples/custom_parser_template.py` @ `4519a2df` · `examples/custom_parser.py.sample`
> **버전:** ⚰️ 이 줄은 «별도 저장소»였을 때의 것입니다 — 판정 386 이후 이 문서는 제품과 «같은 커밋»에 삽니다. 인용한 줄 번호는 «이 커밋의» 파일에서 잰 것입니다

## 0. 두 줄 요약

```
표 모양 파일이면        `BasePipelineParser` 를 상속하고 `match()` · `process_dataframe()` «둘만» 씁니다
표 모양이 아니면        `parse_file(file_path) -> list[dict]` 함수 «하나»를 씁니다
                      🔴 **«미배선 — S-213» — §4 를 «먼저» 읽으십시오**
```

## 1. 어느 길인지 «먼저» 고릅니다

`examples/custom_parser_template.py` 머리 주석(@ `4519a2df`)이 그 갈림을 적습니다 —
그 파일 이름이 "template" 이지만 **«둘 중 하나»일 뿐**이고, 새 파서는 대개 «다른 쪽»에서 출발합니다.

| | 클래스형 | 함수형 |
|---|---|---|
| 언제 | **표 형태 파일이면 거의 항상 이쪽** | pandas 를 안 쓰거나 행/열 구조가 아닌 입력(매트릭스·이진·비정형) |
| 당신이 쓰는 것 | `match()` · `process_dataframe()` «둘» | `parse_file()` «하나» |
| 베이스가 하는 것 | 읽기 · NaN 정리 · DB 전달 | «없음» — 당신이 파일을 통째로 읽습니다 |
| 정본 | `server/parsers/pipeline_base.py` :8 | `examples/custom_parser_template.py` |
| 오늘 도나 | ✅ 로더가 이 하위 클래스를 «찾습니다» | 🔴 **«미배선 — S-213» — §4** |
| 예제 | `examples/custom_parser.py.sample` | 위 template 파일 자체 |

## 2. 🔴 파일을 «어디에» 두나 — 이것부터입니다

```
server/ingestion_workspace/<표>/scripts/
```
`examples/custom_parser.py.sample` 머리 주석이 그렇게 적습니다 —
**`.sample` 은 «로드되지 않습니다».** 실제 파서는 위 경로에 둡니다.
⚠️ **그 트리는 저장소에 안 들어갑니다.** 즉 당신 파서는 «당신 상자의 것»이고, 저장소를 검색해도
안 잡히며, 다른 상자로 저절로 따라가지 않습니다(`pipeline_base.py` :36~40 이 그 사실을 적습니다).

## 3. 클래스형 — 훅 «둘»

```python
import pandas as pd
from pipeline_base import BasePipelineParser

class <당신의>Parser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:        # 훅 ①  :15
        return file_path.lower().endswith('.csv')  # 이름으로도, 첫 줄을 읽어서도 됩니다

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:   # 훅 ②  :22
        df['<컬럼>'] = ...                          # 컬럼 연산 · 타입 캐스팅 · 전처리
        return df
```

베이스가 도는 순서 — `parse()` (`server/parsers/pipeline_base.py` :99):
```
파일  ->  _read_file_to_dataframe  :29   ->  process_dataframe  :22  ->  clean_for_postgres  :56  ->  list[dict]
          (당신이 «오버라이드할 수» 있음)      (당신 것)                  (NaN·NaT·Inf -> None)
```

### 🔴 `_read_file_to_dataframe` 은 밑줄로 시작하지만 «공개 확장점»입니다
`server/parsers/pipeline_base.py` :36~43 이 그것을 «계약으로 승격»한다고 적습니다.
구분자·인코딩·헤더 위치가 다른 소스는 **이 메서드를 오버라이드해서** 대응합니다.
```python
    def _read_file_to_dataframe(self, file_path: str) -> pd.DataFrame:
        return pd.read_csv(file_path, sep='|', encoding='cp949', header=2)
```
기본값은 확장자로 갈립니다(:44~51): `.csv`/`.txt` → `pd.read_csv`, `.xlsx`/`.xls` → `pd.read_excel`,
그 밖은 «경고를 찍고» csv 로 떨어집니다.

### 🔴 `clean_for_postgres` 가 하는 일을 당신이 다시 하지 마십시오
`:56~` — NaN · NaT · Inf 를 JSON 표준의 `None` 으로 바꿉니다. 이것이 없으면 「값이 없었다」가
「값이 `nan` 이다」가 되고, 그건 «값»입니다. 당신 `process_dataframe` 에서 미리 문자열로
채우면 그 구별이 «먼저» 사라집니다.

### 파일 이름 — `get_basename` :84
파일명 끝의 `_<8자리 16진수>` 를 떼어 냅니다(:95~97). 같은 소스가 실행마다 다른 접미를 달고
와도 «같은 이름»으로 읽히게 하는 자리입니다.

## 4. 함수형 — 함수 «하나»

```python
def parse_file(file_path: str) -> list[dict]:
    ...
    return rows_output          # dict 의 리스트. 한 dict = 한 행
```
계약은 그 한 줄이 전부입니다(`examples/custom_parser_template.py` 머리 주석).
그 파일의 예시는 2D 매트릭스를 `{"x":…, "y":…, "z":…}` 좌표 행으로 펴는 것이고,
**pandas 를 한 번도 안 씁니다** — 그것이 이 길을 고르는 이유입니다.

⚠️ **이 길은 베이스가 아무것도 안 해 줍니다** — NaN 정리도, 읽기도, 파일명 정규화도 없습니다.
표 모양 입력에서 이 길을 고르면 §3 의 세 가지를 «당신이 다시 씁니다».

### 🔴🔴 «미배선 — S-213» — 오늘 이 함수를 «집어 가는 자리»가 없습니다 (판정 352, 2026-09-13 실측)
```
워크스페이스 스크립트를 싣는 자리   server/parsers/directory_watcher.py :1146~1172
  그 자리가 하는 일               파일을 exec 한 뒤 `inspect.getmembers(module, inspect.isclass)` —
                                즉 «클래스»만 봅니다. `BasePipelineParser` 의 하위 클래스가 아니면
                                아무것도 안 합니다
  모듈 수준 함수                  «한 번도 안 찾습니다»
제가 뺀 네 갈래(부재를 말하기 전에)  데코레이터 등록 «없음» · 시험만 «없음» ·
                                설정 문자열 «없음»(`:3453` 의 `custom_parser` 는 «로그 문구»입니다) ·
                                명령줄 «없음». `run_auto_update.py` :493~505 도 스크립트를 싣지만
                                그쪽이 찾는 것은 `BaseCollector` 하위 클래스로 «다른 기제»입니다
```
🔴 **그래서 오늘 `parse_file` 만 적어 두면 «조용히 아무 일도 안 일어납니다»** — 오류도 안 납니다.
이 길의 계약은 옮겨 온 템플릿의 «머리 주석»에만 살아 있고, 그것을 읽는 코드가 «없습니다».
📌 그러니 오늘 새 파서를 쓰신다면 **§3 클래스형**으로 쓰십시오 — 표 모양이 아니어도
`_read_file_to_dataframe` 를 오버라이드해서 «당신이 직접 읽으면» 됩니다(§3 의 그 절).
⚠️ **이 절은 「그 길을 없애자」가 아닙니다 — «표시»입니다(판정 352)**. 지우면 「왜 없는가」가 다시 유도되고, 가르치면 운영자가 «침묵»을 받습니다. 짓느냐(워처가 모듈의 함수도 줄도록) 지우느냐는 **S-213** 이 답합니다 — 제품이 그 자리를 «가져야 하는지»는 판정 사항이고,
저장소의 `server/tests/test_the_authoring_guides_name_entry_points_that_exist.py` 가 오늘의 상태를
«잽니다». 그 시험이 빨개지는 날 이 절이 낡은 것이니 그때 고치십시오.

## 5. 만들어 보는 자리

```
server/notebooks/parser_workbench.ipynb      개발 · 검증 · 내보내기
```
`custom_parser.py.sample` 머리 주석이 「이 파일의 모양을 그대로 따른다 — 예시가 둘로 갈라지지
않게 하려는 것」이라고 적습니다. 즉 **워크벤치와 샘플이 «같은 모양»이어야** 하고, 한쪽만 고치면
그 순간 둘이 갈립니다.

## 6. HTML 표가 입력이면 — «라이브러리»가 하나 있습니다

`server/parsers/html_topology_parser.py` (824줄) @ `b95d998b` 의 `HTMLTableGraphParser` 는
병합 셀(`rowspan`/`colspan`)과 불규칙 레이아웃에서 **데이터와 헤더의 관계를 역추적**합니다.
위 두 길 중 «어느 쪽이든» 그것을 부를 수 있습니다 — 파서의 «길»이 아니라 «도구»입니다.

🔴 **그런데 그 사용 설명서는 오늘 낡았습니다. 제 실측입니다:**
```
docs/guide/HTML_TOPOLOGY_PARSER_GUIDE.md @ `8cdd00e8`   머리글 «Last-verified: 2026-07-24»
  그 문서에서 `REFUSED`·`refus`·「격자 원점」  ->  «0건»
소스 server/parsers/html_topology_parser.py @ `b95d998b`
  `REFUSED to parse` :654 · `note_refusal` :809 · `take_refusal` :814 · `clear_refusal` :822
그 행동을 넣은 커밋  `419cd8fa` (2026-08-04) — 「격자 원점을 «두 번» 유도하고 어긋나면 파일을 거절한다」
  그 커밋이 이 파일에 +151 / −51
```
⚠️ **그래서 그 문서를 읽을 때는 「거절 경로가 통째로 빠져 있다」를 알고 읽으십시오.**
파일이 조용히 0건으로 들어오면 그것은 «버그»가 아니라 «거절»일 수 있고, 그 낱말이 그 문서에
없습니다. 📌 이 가이드는 그 문서를 «옮겨 오지 않았습니다» — 낡은 문장을 옮기면 낡음이 «두 벌»이
되기 때문입니다. 저장소 경로로만 가리킵니다.

## 7. 예제 — 이 디렉토리의 `examples/`

```
examples/custom_parser.py.sample        클래스형 — `match()` + `process_dataframe()` 둘. 표 모양의 기본
examples/custom_parser_template.py      함수형 — `parse_file()` 하나. ⚠️ §4 의 벽을 읽고 쓰십시오
```
🔵 **둘 다 «읽는 파일»입니다** — 그대로 복사해 `server/ingestion_workspace/<표>/scripts/` 에 두고
이름과 내용을 바꾸십시오(§2). 이 디렉토리의 파일을 제품이 로드하지 «않습니다».

### 저장소에 «남은» 것들 — 여기 사본이 없고, 경로로만 가리킵니다
```
server/parsers/void_obs_parser.py.sample          운영자가 «손으로 복사하는» shim.
server/parsers/inspection_run_parser.py.sample    존재 이유가 「수정은 `git pull` 하나」라, 이쪽으로
                                                  오면 저장소가 «둘»이 되어 그 이유가 거짓이 됩니다(판정 349)
server/mappers/*.py.sample 일곱                    시험이 바이트를 «라이브 맵퍼»와 대조하는 드리프트
                                                  게이트가 읽습니다 — 사람만 읽는 파일이 «아닙니다»(판정 348)
server/notebooks/parser_workbench.ipynb           개발·검증·내보내기(§5)
```
🔴 **사본을 «두 벌» 만들지 않는 것이 이 표의 요점입니다** — 같은 파일이 두 곳에 있으면 «갈리고»,
갈린 쪽이 조용합니다. 여기 있는 것은 저장소에 «없고», 저장소에 있는 것은 여기 «없습니다».

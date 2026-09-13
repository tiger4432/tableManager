# -*- coding: utf-8 -*-
"""파일 인제션 실행이 «쓸 수 있는 상태 어휘» — 한 자리.

🔴 이 이름이 「이 목록의 상태」가 «아니라» 「이 계열이 쓸 수 있는 어휘」인 것이 중요하다.
   그래서 목록 라우트의 «내용»이 아니라 그 계열의 «어휘»로서 실려 나간다 — 그 구분이 없으면
   다음 사람이 「왜 실패 목록이 SUCCESS 를 말하나」로 읽는다.

실측 2026-09-07 — 이 집합을 «손으로» 적은 자리가 셋이었고 «셋 다» 낡아 있었다:
   database/models.py  status 컬럼 주석      "FAILED", "SUCCESS", "PENDING"     (셋)
   main.py             로그 라우트 독스트링   ALL, SUCCESS, FAILED               (셋)
   client2/admin.html  필터 옵션              ALL / FAILED / SUCCESS             (셋)
그런데 «쓰는» 자리는 다섯이다. 그래서 운영자가 고를 수 없는 상태가 «셋»이었다:
   SUCCESS        parsers/directory_watcher.py:2171 · :2240
   FAILED         parsers/directory_watcher.py:2163 · :2250 · run_watcher.py:394
   PENDING        run_watcher.py:330
   PENDING_RETRY  run_watcher.py:258 · main.py:5616
   SKIPPED        parsers/directory_watcher.py:2025

⚠️ `ALL` 은 «여기 없다». 그건 상태가 아니라 「거르지 않음」이고, 한 이름에 두 뜻을 담는 순간
   「상태 다섯」과 「고를 수 있는 것 여섯」이 갈라진다.
⛔ 선언(config)으로 내지 않는다. 실행의 «생애 주기»는 이 코드의 어휘이지 도메인이 아니다 —
   운영자가 새 상태를 만들려면 그것을 «읽는 코드»가 같이 있어야 한다 (총괄 판정 25).
"""

#: 이 계열이 쓸 수 있는 상태 «전부». 화면의 필터 목록도 여기서 나온다.
FILE_INGESTION_STATUS_VOCABULARY = (
    "SUCCESS",
    "FAILED",
    "PENDING",
    "PENDING_RETRY",
    "SKIPPED",
)

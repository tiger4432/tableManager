# -*- coding: utf-8 -*-
"""체인 — 선언이 어떤 형태든 «맵퍼 하나»로 이어지는 다섯 걸음이 여기 산다.

> 소유자 2026-09-17: 「체인은 어떤 형태의 선언이든 맵퍼로 이어지고 트랜잭션 - 아웃박스 -
>  트리거 - 맵퍼 실행 - 페이로드 및 업서트 이거만 하면됨」 · 「모든 체인은 server/chain
>  안에서만 코드 존재」

⚰️ THIS DOCSTRING SAID 「NOT THE CHAIN'S CODE」 AND NAMED THREE FLAT MODULES
(`chain_ingestion_worker.py`, `chain_replay.py`) as where the work really lived. All three
moved in, and the enrich half - a DECLARATION KIND, not a neighbour - moved in after them
(`chain/enrichment/`), with `keyset_scan` and `session_contract`, which nothing outside the
chain calls.

⛔ TWO NAMES DELIBERATELY STAY FLAT, AND IT IS NOT AN OVERSIGHT: `chain_bindings` and
`mapper_sdk`. The owner's own mapper files - `server/mappers/*.py`, gitignored, read but
never edited - import them by their TOP-LEVEL spelling, and
`directory_watcher.OPERATOR_IMPORT_NAMES` writes that promise down with a gate scoring it:
「a package that swallowed one would break files this repo cannot see, on machines it cannot
reach」. Moving them would satisfy one instruction by breaking another.
"""

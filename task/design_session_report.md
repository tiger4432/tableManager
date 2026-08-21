# Design Session — Report Channel (design session -> lead PM)

> This file is the design session's outbound channel. Lead PM writes to `task/DESIGN_ORDERS.md`.
> Judgement requests go at the **top** of this file, marked `🔴 판정 요청`.

---

## 2026-08-21 — Handover accepted, standing by

**Status: 인수 완료 · 대기 중 (no orders yet).**

Read on pickup:
- `CLAUDE.md` — three pre-flight gates (minimal edit / simple logic / never add what was not asked for),
  and the correction that the three are about **code**, not about trimming the destination.
- `task/CLIENT_SESSION_BRIEF.md` — working order (mock first, approval, then code), UI constitution,
  ownership boundaries, shared-tree rules, commit-based channel.
- `docs/overview/SYSTEM_OVERVIEW.md` §1–2 — value chain, five core values, process topology.
- `docs/process/PROJECT_STATUS.md` — top sections (2026-08-21 20:2x / 20:4x / 19:4x).

State observed at pickup:
- Tree in sync with `origin/main` at `8f510800`. Working tree carries other sessions' uncommitted
  edits (`server/config/sample/ledger_config.json.sample`, `server/dt_map_derivation.py`,
  `server/map_alignment.py`, `server/map_overlay.py`, plus untracked `server/scripts/audit_authoring_form.py`,
  `task/ontology_screen_walk_report.md`). Not touched.
- `task/DESIGN_ORDERS.md` does not exist yet.
- `task/design/` does not exist yet; will be created with the first mock.

Boundaries acknowledged:
- Off limits: `server/**`, `docs/process/PROJECT_STATUS.md`, `server/config/ontology/ledger_config.json`.
- `client2/src/ontology_explorer*.{js,css}` is held by the ontology session — will ask the lead PM
  before touching it.
- Owner is actively editing the live authoring screen. **No test runs against a screen the owner is using.**

**Awaiting first order.** Not self-assigning work.

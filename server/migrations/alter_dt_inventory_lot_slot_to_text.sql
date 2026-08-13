-- ============================================================================
-- dt_inventory.dt_lot / dt_slot : double precision -> character varying
-- ============================================================================
-- SCHEMA_CANON R1 — 식별자는 절대 수치형이 아니다.
--
-- 이 컬럼들은 확정된 (lot, slot)의 집인데 `double precision`으로 선언돼 있었다.
-- 이 시스템의 lot id는 `DT-2601-001` / `CL-2601-005-A5` 같은 «문자열»이고, 슬롯은
-- `01` 처럼 선행 0을 갖는다. 수치형은 둘 다 담지 못한다 —
--   * 문자열 lot 은 애초에 들어가지 않고,
--   * 슬롯 `01` 은 `1` 이 되어 조용히 다른 값이 된다.
--
-- 🔴 config 만 고쳐서는 이 결함이 «절대» 사라지지 않는다.
--    `models.sync_dynamic_tables_schema` 는 컬럼을 ADD 만 한다. 타입은 손대지 않는다.
--    그래서 `table_config.json` 의 `"number" -> "string"` 수정은 선언만 바꾸고 물리
--    컬럼을 영원히 `double precision` 으로 남긴다. 이 파일이 그 나머지 절반이다.
--
-- 적용 대상 판정(2026-08-13, 두 개발 DB 전수 스윕):
--   assy_manager : double precision, 251행, **0행 채움**  -> 변환 손실 없음
--   assy_qa      : 이미 character varying (11행 채움)      -> 이 스크립트는 no-op
--   이 박스에서 lot/slot 이름을 가진 컬럼 중 수치형은 **이 둘뿐**이었다.
--
-- ⚠️ 운영에 값이 «있는» 경우: `USING ::text` 가 변환한다. PostgreSQL 은 정수값
--    double 을 소수점 없이 렌더하므로 `2601001` -> `'2601001'` 이지만, 소수부가 있는
--    값이 있었다면 `'2601001.5'` 가 된다. 그런 값이 있는지 먼저 세는 질의가 아래 있다.
--
-- 멱등: 이미 문자형이면 아무것도 하지 않는다. 두 번 돌려도 안전하다.
-- 역방향: `alter_dt_inventory_lot_slot_to_text_reverse.sql` — 숫자로 되돌릴 수 없는
--         값이 하나라도 있으면 **거절한다**. 조용히 깨뜨리지 않는다.
-- ============================================================================

-- 사전 점검 (읽기 전용) — 소수부를 가진 값이 있나. 0이 아니면 위 주의사항을 읽을 것.
--   SELECT count(*) FROM public.dt_inventory
--    WHERE (dt_lot IS NOT NULL AND dt_lot <> trunc(dt_lot))
--       OR (dt_slot IS NOT NULL AND dt_slot <> trunc(dt_slot));

DO $$
DECLARE
    t text;
BEGIN
    SELECT data_type INTO t
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'dt_inventory'
       AND column_name = 'dt_lot';

    IF t IS NULL THEN
        RAISE NOTICE 'dt_inventory.dt_lot 가 없다 — 건너뛴다';
    ELSIF t IN ('character varying', 'text') THEN
        RAISE NOTICE 'dt_inventory.dt_lot 는 이미 % 다 — 건너뛴다', t;
    ELSE
        EXECUTE 'ALTER TABLE public.dt_inventory '
                'ALTER COLUMN dt_lot TYPE character varying USING dt_lot::text';
        RAISE NOTICE 'dt_inventory.dt_lot : % -> character varying', t;
    END IF;

    SELECT data_type INTO t
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'dt_inventory'
       AND column_name = 'dt_slot';

    IF t IS NULL THEN
        RAISE NOTICE 'dt_inventory.dt_slot 가 없다 — 건너뛴다';
    ELSIF t IN ('character varying', 'text') THEN
        RAISE NOTICE 'dt_inventory.dt_slot 는 이미 % 다 — 건너뛴다', t;
    ELSE
        EXECUTE 'ALTER TABLE public.dt_inventory '
                'ALTER COLUMN dt_slot TYPE character varying USING dt_slot::text';
        RAISE NOTICE 'dt_inventory.dt_slot : % -> character varying', t;
    END IF;
END $$;

-- ============================================================================
-- REVERSE : dt_inventory.dt_lot / dt_slot  character varying -> double precision
-- ============================================================================
-- 🔴 이 역방향은 «되돌리기»가 아니라 «손실»이 될 수 있다. 그래서 조건부다.
--
-- 앞 방향(수치 -> 문자)은 항상 안전하다. 뒤 방향은 아니다 — `DT-2601-001` 은 숫자가
-- 아니고, 슬롯 `01` 은 숫자로 가면 `1` 이 되어 **돌아올 때 다른 값이 된다**.
-- 그러므로 이 스크립트는 되돌릴 수 «없는» 값이 하나라도 있으면 **거절하고 멈춘다.**
-- 조용히 NULL 로 만들거나 잘라 넣지 않는다.
--
-- 거절당했다면 그것이 답이다: 그 컬럼은 애초에 수치형일 수 없었고, 앞 방향이 옳았다.
-- 정말 되돌려야 한다면 먼저 그 값들을 어떻게 할지 «판정»하고 오라.
--
-- 선행 0 주의: `'01'` 은 정규식을 통과하지만 되돌리면 `1` 이 된다. 그래서 값이 하나라도
-- 있으면 통과 여부와 무관하게 경고를 낸다.
-- ============================================================================

DO $$
DECLARE
    bad    bigint;
    filled bigint;
    t      text;
BEGIN
    SELECT data_type INTO t
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'dt_inventory'
       AND column_name = 'dt_lot';

    IF t IS NULL THEN
        RAISE NOTICE 'dt_inventory.dt_lot 가 없다 — 건너뛴다';
        RETURN;
    END IF;

    IF t NOT IN ('character varying', 'text') THEN
        RAISE NOTICE 'dt_inventory.dt_lot 는 이미 % 다 — 건너뛴다', t;
        RETURN;
    END IF;

    -- 되돌릴 수 없는 값을 «전수» 센다. 표본이 아니다.
    SELECT count(*) INTO bad
      FROM public.dt_inventory
     WHERE (dt_lot  IS NOT NULL AND btrim(dt_lot)  <> '' AND btrim(dt_lot)  !~ '^-?[0-9]+(\.[0-9]+)?$')
        OR (dt_slot IS NOT NULL AND btrim(dt_slot) <> '' AND btrim(dt_slot) !~ '^-?[0-9]+(\.[0-9]+)?$');

    IF bad > 0 THEN
        RAISE EXCEPTION
          '거절: dt_inventory 에 숫자로 되돌릴 수 없는 dt_lot/dt_slot 값이 %건 있다. '
          '되돌리면 그 행들을 잃는다. 앞 방향(문자형)이 옳았다는 뜻이므로, 정말 필요하면 '
          '그 값들을 어떻게 할지 먼저 판정하고 오라.', bad;
    END IF;

    SELECT count(dt_lot) + count(dt_slot) INTO filled FROM public.dt_inventory;
    IF filled > 0 THEN
        RAISE WARNING
          '값이 %건 있다. 전부 숫자 형태라 변환은 되지만 선행 0 은 사라진다 '
          '(슬롯 ''01'' -> 1). 그래도 진행한다.', filled;
    END IF;

    EXECUTE 'ALTER TABLE public.dt_inventory '
            'ALTER COLUMN dt_lot TYPE double precision USING nullif(btrim(dt_lot), '''')::double precision';
    EXECUTE 'ALTER TABLE public.dt_inventory '
            'ALTER COLUMN dt_slot TYPE double precision USING nullif(btrim(dt_slot), '''')::double precision';
    RAISE NOTICE 'dt_inventory.dt_lot / dt_slot -> double precision';
END $$;

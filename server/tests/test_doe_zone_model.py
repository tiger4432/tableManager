"""DOE ZONE MODEL — the server half, scored against the SHARED contract vectors.

The file being scored is `contracts/doe_band_rules/vectors.json`, and it is the same file
`contracts/doe_band_rules/client_harness.mjs` reads. That is the whole point: a rule that
lives in one language drifts, and the drift is invisible because both sides keep passing
their own tests. Nothing here hardcodes an expectation — every assertion comes out of the
contract file, so deleting a case from the contract removes coverage LOUDLY (see
`test_every_vector_group_is_consumed_or_declared_client_only`).

WHAT THIS PINS (and what it deliberately does not):
  * stack_cases        → `stack_state`      4-state height reader (ok/blank/invalid/marker)
  * zone_extent_cases  → `mid_zone`/`zone_layers`   the geometry itself
  * plan_cases         → `validate_zone_plan`  V1-V6 + W-DUP-MAT, as SETS of rule ids
  * material_token_cases → `parse_material_token`/`material_pool_key`
  * demand_cases       → `zone_demand`
  * rollup_cases       → `material_rollup_rows`
  * remaining_cases    → `remaining_state`
  * legacy_band_cases  → `bands_to_zones`   migration AND its refusals
  * tsv/paste/roundtrip → CLIENT ONLY. Excel clipboard parsing has no server counterpart;
    the server never sees a pasted grid. Declared, not silently skipped.

THERE ARE NO OVERLAP OR GAP TESTS, and their absence is a result rather than an omission.
The three zones tile `1..STACK` by construction, so a layer covered twice or left uncovered
is not a state this geometry can reach. The band model's B1/B2/B5/B6/B4/B9 became
UNSTATEABLE, not relaxed — B9's hazard is the one that survived, and it is V5.

STACK 0 = MARKER (U9, vectors version 3). An explicit 0 declares a 상태 표시 값: known-empty
zones ([]/known:true — distinct from unreadable's None/known:false), zero demand however
much is painted, absent from the rollup, and V6 is the ONLY message on such a row (V4/V3/
W-DUP suppressed). Blank is unchanged — absence still blocks (V5); 0 is a declaration.
"""
import json
import pathlib

import pytest

import transfer_plan


def _vectors():
    p = (pathlib.Path(__file__).resolve().parents[2]
         / "contracts" / "doe_band_rules" / "vectors.json")
    assert p.exists(), f"공유 계약 벡터가 없다: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def _cases(group, key):
    """`$comment`(=`$why`만 있는) 항목을 걸러낸 실제 케이스들."""
    return [c for c in _vectors()[group] if key in c]


# 서버가 소비하는 그룹 / 클라 전용이라 서버 대응물이 없는 그룹.
# 새 그룹이 벡터 파일에 생기면 아래 테스트가 실패한다 — 등록만 지우면 계약이 그 축을
# 조용히 놓친다.
_SERVER_CONSUMED = {
    "stack_cases", "zone_extent_cases", "plan_cases", "material_token_cases",
    "demand_cases", "rollup_cases", "remaining_cases", "legacy_band_cases",
}
_CLIENT_ONLY = {"tsv_cases", "paste_cases", "roundtrip_cases"}


def test_every_vector_group_is_consumed_or_declared_client_only():
    # v3 = the marker (STACK 0) contract. Scoring an older snapshot would pass while
    # missing the U9 semantics entirely — the version is part of what "consumed" means.
    assert _vectors()["version"] >= 3, "계약 벡터가 v3(marker 의미론) 이전 스냅숏이다"
    present = {k for k in _vectors() if k.endswith("_cases")}
    assert present == (_SERVER_CONSUMED | _CLIENT_ONLY), (
        "벡터 그룹 구성이 바뀌었다. 새 그룹을 추가했다면 그것을 소비하는 서버 테스트를 쓰고 "
        "_SERVER_CONSUMED에 등록하거나, 서버 대응물이 없다면 _CLIENT_ONLY에 **이유와 함께** "
        f"등록하라. 파일: {sorted(present)}")


# ---------------------------------------------------------------------------
# STACK — 3상태 높이 판정기
# ---------------------------------------------------------------------------

def test_stack_state_matches_the_shared_contract():
    seen = 0
    for c in _cases("stack_cases", "state"):
        seen += 1
        val, st = transfer_plan.stack_state({"stack": c["stack"]})
        assert st == c["state"], f"{c['name']}: state {st!r} != {c['state']!r}"
        assert val == c["value"], f"{c['name']}: value {val!r} != {c['value']!r}"
    assert seen >= 12, "stack 벡터가 사라졌다 (v3: marker 케이스 포함 12개)"


def test_the_single_integer_reader_is_shared_with_bin():
    """🔴 STACK과 BIN이 **같은 판정기**를 쓴다는 것이 계약이다.

    숫자 파서가 둘이면 `'0x10'`이 한쪽에서 16, 다른 쪽에서 0이 된다 — 실제로 그렇게 16이
    DB에 쓰인 적이 있다. 벡터 파일도 `hex_bin_refuses`에서 "Same integer reader as STACK"
    이라고 못박는다. 이름이 같은 두 구현이 아니라 **한 구현**임을 여기서 고정한다.
    """
    assert transfer_plan.stack_state({"stack": "0x10"})[1] == transfer_plan.BAND_TO_INVALID
    assert transfer_plan.parse_material_token("MID1:0x10")["ok"] is False
    # 같은 함수를 타는지 — `_int_state`를 부수면 둘 다 깨져야 한다.
    assert transfer_plan._int_state("0x10") == (None, transfer_plan.BAND_TO_INVALID)


# ---------------------------------------------------------------------------
# 구역 기하 — MID 범위와 구역별 층
# ---------------------------------------------------------------------------

def _encode_layers(layers):
    """벡터의 층 표기 규약: null → null · [] → [] · 그 외 [처음, 끝, 개수]."""
    if layers is None:
        return None
    if not layers:
        return []
    return [layers[0], layers[-1], len(layers)]


def test_zone_extents_match_the_shared_contract():
    seen = 0
    for c in _cases("zone_extent_cases", "row"):
        seen += 1
        row, exp = c["row"], c["mid"]
        got = transfer_plan.mid_zone(row)
        assert got == exp, f"{c['name']}: mid {got} != {exp}"
        for zone, exp_layers in c["layers"].items():
            got_layers = _encode_layers(transfer_plan.zone_layers(row, zone))
            assert got_layers == exp_layers, (
                f"{c['name']}/{zone}: layers {got_layers} != {exp_layers}")
    assert seen >= 7, "zone_extent 벡터가 사라졌다 (v3: marker 케이스 포함 7개)"


def test_unreadable_height_yields_none_never_an_empty_list():
    """🔴 `[]`와 `None`을 접으면 16층 스택이 15층이 된다.

    벡터가 두 상태를 **같은 파일 안에서** 나란히 고정한다: STACK 2 + 1H·TOP의 MID는
    `size 0 / known true`(정상), STACK 판독 불가는 `known false`. 이 테스트는 그 둘이
    서로 다른 값으로 나오는지만 본다 — 하나로 접는 구현은 위 벡터 테스트도 통과할 수 있다
    (기대값이 `[]`인 행과 `null`인 행을 모두 `[]`로 만들면 후자만 깨지므로 실은 못 통과하지만,
    의도를 코드에 남긴다).
    """
    legit = {"value": "E", "stack": 2, "mat_1h": ["H_01"], "mat_mid": [], "mat_top": ["T_01"]}
    broken = {"value": "X", "stack": "0x10", "mat_1h": [], "mat_mid": ["M_01"], "mat_top": []}
    assert transfer_plan.zone_layers(legit, "mat_mid") == []
    assert transfer_plan.zone_layers(broken, "mat_mid") is None
    assert transfer_plan.mid_zone(legit)["known"] is True
    assert transfer_plan.mid_zone(broken)["known"] is False


# ---------------------------------------------------------------------------
# 차단 규칙 V1~V5 (+ W-DUP-MAT)
# ---------------------------------------------------------------------------

def test_zone_plan_verdicts_match_the_shared_contract():
    """규칙 id의 **집합**이 일치해야 한다(순서 무관 — 벡터 파일이 그렇게 선언한다)."""
    seen = 0
    for c in _cases("plan_cases", "values"):
        seen += 1
        out = transfer_plan.validate_zone_plan(c["values"])
        blocks = {b["rule"] for b in out["blocks"]}
        warns = {w["rule"] for w in out["warns"]}
        assert blocks == set(c["expect_blocks"]), (
            f"{c['name']}: blocks {sorted(blocks)} != {sorted(c['expect_blocks'])}")
        assert warns == set(c["expect_warns"]), (
            f"{c['name']}: warns {sorted(warns)} != {sorted(c['expect_warns'])}")
        assert out["ok"] is (len(c["expect_blocks"]) == 0), f"{c['name']}: ok flag"
    assert seen >= 15, "plan 벡터가 사라졌다 (v3: marker 케이스 포함 15개+)"


def test_every_blocking_rule_id_is_exercised_by_the_contract():
    """벡터가 V1~V5와 W-DUP-MAT을 **전부** 발화시키는지 확인한다.

    이 테스트가 없으면 규칙 하나를 통째로 구현하지 않아도 초록불이 켜질 수 있다 — 그 규칙을
    발화시키는 케이스가 벡터에서 빠지는 순간 아무도 모르게 커버리지가 사라진다.
    """
    fired = set()
    for c in _cases("plan_cases", "values"):
        out = transfer_plan.validate_zone_plan(c["values"])
        fired |= {b["rule"] for b in out["blocks"]}
        fired |= {w["rule"] for w in out["warns"]}
    assert fired == {"V1", "V2", "V3", "V4", "V5", "V6", "W-DUP-MAT"}, sorted(fired)


def test_v5_blocks_first_and_suppresses_the_extent_rules():
    """🔴 읽을 수 없는 STACK은 **다른 무엇보다 먼저** 막는다.

    다른 모든 판정이 계산할 수 없는 층 수에서 유도되므로, V5가 난 행에서 구역을 추측하면
    같은 행에 모순된 두 메시지가 나간다. 벡터
    `unreadable_stack_blocks_and_suppresses_the_extent_rules`가 이것을 고정한다.
    """
    out = transfer_plan.validate_zone_plan(
        [{"value": "X", "stack": "0x10", "mat_1h": [], "mat_mid": [], "mat_top": []}])
    assert {b["rule"] for b in out["blocks"]} == {"V5"}


def test_v3_is_a_property_of_the_whole_plan_not_of_one_row():
    """두 토큰이 **서로 다른 값**에 있어도 잡아야 한다 — 행 단위 구현은 이걸 통과시킨다."""
    rows = [{"value": "A", "stack": 8, "mat_1h": [], "mat_mid": ["MID1_03"], "mat_top": []},
            {"value": "B", "stack": 8, "mat_1h": [], "mat_mid": ["MID1"], "mat_top": []}]
    assert {b["rule"] for b in transfer_plan.validate_zone_plan(rows)["blocks"]} == {"V3"}
    # 행 하나씩 보면 어느 쪽도 걸리지 않는다 = 이 테스트가 실제로 전체 성질을 재고 있다.
    for r in rows:
        assert transfer_plan.validate_zone_plan([r])["blocks"] == []


# ---------------------------------------------------------------------------
# STACK 0 = MARKER (U9) — the vectors score the outcomes; these pin the AXES.
# ---------------------------------------------------------------------------

def test_marker_is_a_declaration_and_blank_is_absence():
    """🔴 The two must not merge in either direction.

    Folding 0 into blank turns a declared marker into "not typed yet" (V5 nags at a legal
    row); folding blank into 0 turns every half-typed row into a marker (V5 never fires and
    a plan goes out half-written). `Number('  ') === 0` on the client side is exactly the
    accident the whitespace case guards against.
    """
    assert transfer_plan.stack_state({"stack": 0}) == (0, transfer_plan.STACK_MARKER)
    assert transfer_plan.stack_state({"stack": "0"}) == (0, transfer_plan.STACK_MARKER)
    assert transfer_plan.stack_state({"stack": ""})[1] == transfer_plan.BAND_TO_BLANK
    assert transfer_plan.stack_state({"stack": "   "})[1] == transfer_plan.BAND_TO_BLANK
    # Only EXACTLY 0 — a negative is still a typo, and it keeps its value for the message.
    assert transfer_plan.stack_state({"stack": -3}) == (-3, transfer_plan.BAND_TO_INVALID)
    # `_int_state` itself is untouched: layer bounds and BINs still refuse 0. The promotion
    # lives in `stack_state` ALONE — a second reader that learned "0 is fine" would let
    # `MID1:0` through as a BIN.
    assert transfer_plan._int_state(0) == (0, transfer_plan.BAND_TO_OK)
    assert transfer_plan.parse_material_token("MID1:0")["ok"] is False


def test_marker_extents_are_known_empty_not_unknowable():
    """🔴 Mirror of `test_unreadable_height_yields_none_never_an_empty_list`, other side.

    marker = []/known:true (a real zero, like the E-row's 0-layer MID) while unreadable =
    None/known:false. Fold marker into unreadable and V5 nags at a legal row; fold
    unreadable into marker and a typo'd height silently demands nothing behind a clean
    screen. The MID content on the marker row is deliberate: the extent stays [] anyway —
    the contradiction is V6's to report, not the geometry's to legitimize.
    """
    marker = {"value": "F", "stack": 0, "mat_1h": [], "mat_mid": ["M_01"], "mat_top": []}
    broken = {"value": "X", "stack": "0x10", "mat_1h": [], "mat_mid": ["M_01"], "mat_top": []}
    assert transfer_plan.mid_zone(marker) == {"from": None, "to": None, "size": 0, "known": True}
    assert transfer_plan.mid_zone(broken)["known"] is False
    for z in ("mat_1h", "mat_mid", "mat_top"):
        assert transfer_plan.zone_layers(marker, z) == []
    assert transfer_plan.zone_layers(broken, "mat_mid") is None
    # And demand is zero HOWEVER much is painted — painted cells are the message
    # (96 cells are in that state), not a multiplier.
    assert transfer_plan.zone_demand(marker, "mat_mid", 9999) == {
        "layers": 0, "total": 0, "share": 0}


def test_v6_is_the_only_message_on_a_marker_row():
    """🔴 Suppression scope. The row below trips, on a non-marker row, V4 (dangling '_'),
    W-DUP-MAT (duplicate in one zone) — and V5 would fire were 0 still invalid. On a marker
    row ALL of them stay silent and V6 alone reports; two contradictory instructions about
    one row (fix the token vs remove the materials) is worse than one.
    """
    row = {"value": "F", "stack": 0,
           "mat_1h": ["ABC_", "ABC_"], "mat_mid": ["M_01"], "mat_top": []}
    out = transfer_plan.validate_zone_plan([row])
    assert {b["rule"] for b in out["blocks"]} == {"V6"}
    assert out["warns"] == []
    # And a clean marker row is SILENT — a validator that nags at a declared marker
    # teaches people to ignore it.
    clean = {"value": "F", "stack": 0, "mat_1h": [], "mat_mid": [], "mat_top": []}
    assert transfer_plan.validate_zone_plan([clean]) == {"ok": True, "blocks": [], "warns": []}


def test_v3_exclusion_is_the_marker_state_not_the_token():
    """Fixture-activation proof: the SAME token pair does block V3 once the marker row's
    stack becomes a real height. Without this control, an implementation that never fed
    any second row into the V3 scan would pass the vector's marker case too.
    """
    real = {"value": "A", "stack": 8, "mat_1h": [], "mat_mid": ["MID1_03"], "mat_top": []}
    marker = {"value": "F", "stack": 0, "mat_1h": [], "mat_mid": ["MID1"], "mat_top": []}
    out = transfer_plan.validate_zone_plan([real, marker])
    assert {b["rule"] for b in out["blocks"]} == {"V6"}   # not V3 — demandless token
    unmarked = dict(marker, stack=8)
    out2 = transfer_plan.validate_zone_plan([real, unmarked])
    assert {b["rule"] for b in out2["blocks"]} == {"V3"}  # the axis is alive


def test_marker_row_is_absent_from_the_rollup_not_present_with_zero():
    """Beyond the vector: assert the marker's pool key NEVER appears, even as used 0 —
    a 'MID9 · 사용 0' row would read as "planned, costs nothing" and invite an
    availability query for material nobody is demanding.
    """
    rows = [
        {"value": "A", "stack": 2, "mat_1h": [], "mat_mid": ["M_01"], "mat_top": []},
        {"value": "F", "stack": 0, "mat_1h": [], "mat_mid": ["MID9"], "mat_top": []},
    ]
    got = transfer_plan.material_rollup_rows(rows, lambda v: {"A": 6, "F": 50}[v])
    assert [r["lot"] for r in got] == ["M"]
    assert all("MID9" not in json.dumps(r) for r in got)


# ---------------------------------------------------------------------------
# 자재 토큰 문법 + 풀 키
# ---------------------------------------------------------------------------

def test_material_tokens_match_the_shared_contract():
    seen = 0
    for c in _cases("material_token_cases", "ok"):
        seen += 1
        got = transfer_plan.parse_material_token(c["raw"])
        assert got["ok"] is c["ok"], f"{c['name']}: ok {got['ok']} != {c['ok']}"
        if not c["ok"]:
            assert got["reason"], f"{c['name']}: 거부에는 사유가 있어야 한다"
            continue
        for field in ("lot", "slot", "bin", "scope"):
            assert got[field] == c[field], (
                f"{c['name']}/{field}: {got[field]!r} != {c[field]!r}")
    assert seen >= 15, "material_token 벡터가 사라졌다"


def test_pool_keys_stay_distinct_where_the_contract_says_they_must():
    """🔴 실제 사고의 회귀 테스트. U+001F로 이었던 판에서 문자가 쓰기 과정에 삭제돼
    `MID1_12:3`과 `MID11_2:3`이 둘 다 "MID1123"이 됐고, 무관한 두 풀이 한 행으로 합쳐져
    사용량이 더해졌다. 구분자를 고르고 있다면 그것이 신호다 — 키는 `json.dumps`다.
    """
    seen = 0
    for c in _cases("material_token_cases", "distinct_from"):
        seen += 1
        a = transfer_plan.material_pool_key(transfer_plan.parse_material_token(c["raw"]))
        b = transfer_plan.material_pool_key(
            transfer_plan.parse_material_token(c["distinct_from"]))
        assert a is not None and b is not None, c["name"]
        assert a != b, f"{c['name']}: {c['raw']!r}와 {c['distinct_from']!r}가 같은 키({a})"
    assert seen >= 3, "pool key 구별 벡터가 사라졌다"


def test_pool_key_carries_no_separator_at_all():
    """구분자 기반 구현을 구조적으로 배제한다: 키는 JSON 배열이어야 하고, 그래서
    `null`(로트 전체)이 문자열 `"null"`(그렇게 이름 붙은 슬롯)과 구별된다."""
    whole_lot = transfer_plan.material_pool_key(transfer_plan.parse_material_token("MID1"))
    named_null = transfer_plan.material_pool_key(
        transfer_plan.parse_material_token("MID1_null"))
    assert json.loads(whole_lot) == ["MID1", None, 1]
    assert json.loads(named_null) == ["MID1", "null", 1]


# ---------------------------------------------------------------------------
# 소요 산술
# ---------------------------------------------------------------------------

def test_zone_demand_matches_the_shared_contract():
    seen = 0
    for c in _cases("demand_cases", "row"):
        seen += 1
        got = transfer_plan.zone_demand(c["row"], c["zone"], c["painted"])
        assert got == c["expect"], f"{c['name']}: {got} != {c['expect']}"
        # 벡터가 "반올림/내림이면 이 값" 을 함께 적어 둔 케이스는 그 값이 **아님**도 본다.
        for wrong_key in ("wrong_if_rounded", "wrong_if_floored"):
            if wrong_key in c:
                assert got["share"] != c[wrong_key], f"{c['name']}: {wrong_key}"
    assert seen >= 8, "demand 벡터가 사라졌다 (v3: marker 케이스 포함 8개)"


def test_rollup_rows_match_the_shared_contract():
    seen = 0
    for c in _cases("rollup_cases", "values"):
        seen += 1
        painted = c["painted"]
        rows = transfer_plan.material_rollup_rows(c["values"], lambda v: painted.get(v, 0))
        got = [{"pool": [r["lot"], r["slot"], r["bin"]], "used": r["used"]} for r in rows]
        assert got == c["expect"], f"{c['name']}: {got} != {c['expect']}"
    assert seen >= 5, "rollup 벡터가 사라졌다 (v3: marker 케이스 포함 5개)"


def test_remaining_state_matches_the_shared_contract():
    seen = 0
    for c in _cases("remaining_cases", "availability"):
        seen += 1
        got = transfer_plan.remaining_state(c["availability"], c["used"])
        assert got["value"] == c["expect"]["value"], f"{c['name']}: value"
        assert got["reliable"] is c["expect"]["reliable"], f"{c['name']}: reliable"
        if "reason_contains" in c:
            assert c["reason_contains"] in got["reason"], f"{c['name']}: reason"
        # 🔴 「미상」의 세 상황은 서로 다른 문장이어야 한다. 하나의 generic 「미상」으로
        #    접으면 숨기는 행위 자체가 무의미해진다(사용자의 다음 행동이 다르다).
        for other in c.get("reason_differs_from", []):
            assert transfer_plan.remaining_state(other, c["used"])["reason"] != got["reason"], (
                f"{c['name']}: {other['status']}와 사유가 같다")
    assert seen >= 6, "remaining 벡터가 사라졌다"


# ---------------------------------------------------------------------------
# 폐기 모델 읽기 (bands -> zones)
# ---------------------------------------------------------------------------

def test_legacy_bands_migrate_or_are_refused_per_the_shared_contract():
    """🔴 `map_split_registry.bands`에는 실계획이 들어 있고, legend 저장은 `replace_map`이다.

    읽지 못하면 그 맵을 여는 순간 화면이 비고 다음 편집 한 번이 계획을 빈 집합으로 지운다.
    그리고 **표현할 수 없는 배치는 접지 않고 거부한다** — 접은 결과를 되쓰는 것이 이 영역이
    존재하는 이유인 그 결함이다.
    """
    seen, refusals, migrations = 0, 0, 0
    for c in _cases("legacy_band_cases", "expect"):
        seen += 1
        got = transfer_plan.bands_to_zones(c["bands"])
        exp = c["expect"]
        assert got["ok"] is exp["ok"], f"{c['name']}: ok {got['ok']} != {exp['ok']}"
        if not exp["ok"]:
            refusals += 1
            assert got.get("reason"), f"{c['name']}: 거부에는 사유가 있어야 한다"
            continue
        migrations += 1
        for field in ("stack", "mat_1h", "mat_mid", "mat_top"):
            assert got[field] == exp[field], (
                f"{c['name']}/{field}: {got[field]!r} != {exp[field]!r}")
    assert seen >= 8, "legacy_band 벡터가 사라졌다"
    # 픽스처가 **두 축을 모두** 활성화하는지 테스트 자신이 단언한다. 거부 케이스가 하나도
    # 없으면 "무조건 성공"을 돌려주는 구현이 통과한다.
    assert refusals >= 3 and migrations >= 4, (refusals, migrations)


def test_a_lossy_collapse_would_be_caught():
    """거부 축이 실제로 살아 있는지 — 4구간을 3구역으로 접는 구현은 여기서 죽는다."""
    four = [{"seq": 1, "to": 1, "materials": ["A_01"]},
            {"seq": 2, "to": 5, "materials": ["B_01"]},
            {"seq": 3, "to": 15, "materials": ["C_01"]},
            {"seq": 4, "to": 16, "materials": ["D_01"]}]
    assert transfer_plan.bands_to_zones(four)["ok"] is False
    # 그리고 3구간(같은 모양에서 하나만 뺀 것)은 정상 통과한다 = 길이만 보고 막는 것이 아니다.
    three = [four[0], four[2], four[3]]
    ok = transfer_plan.bands_to_zones(three)
    assert ok["ok"] is True and ok["stack"] == 16 and ok["mat_mid"] == ["C_01"]


def test_non_increasing_to_is_refused_even_when_the_shape_still_fits_three_zones():
    """🔴 뮤테이션이 살아남아 드러난 구멍을 메운다.

    벡터의 `non_increasing_to_is_REFUSED`는 `[to 10, to 5]`인데, 이 배치는 역전 검사를 빼도
    "중간 구간이 2개"에서 어차피 거부된다 — 즉 그 케이스만으로는 **역전 검사 자체가 살아
    있는지 증명되지 않는다**(`if val <= prev`를 통째로 없앤 판이 통과했다).

    `[to 1, to 1]`이 그 축을 실제로 활성화한다: 역전 검사가 없으면 두 번째 구간이 `(2,1)`인
    빈 구간이 되고, 첫 구간이 1H로 빠져 나가면서 남는 것이 하나뿐이라 **`ok: True`로 통과해
    버린다** — 사용자가 만든 적 없는 1H+MID 배치가 만들어진다. 층 하나짜리 계획이 조용히
    두 구역이 된다.
    """
    got = transfer_plan.bands_to_zones([{"seq": 1, "to": 1, "materials": ["A_01"]},
                                        {"seq": 2, "to": 1, "materials": ["B_01"]}])
    assert got["ok"] is False, got
    assert "크지 않습니다" in got["reason"]


# ---------------------------------------------------------------------------
# 저장 컬럼 읽기 — 계약 벡터가 다루지 않는 **전송 형태**
# ---------------------------------------------------------------------------

def test_zone_column_json_array_is_not_comma_split():
    """🔴 writer는 `JSON.stringify([...])`를 쓴다. 그 문자열에 쉼표 분해를 걸면
    `'["MID1"'`이 자재 이름이 된다 — 벡터는 이미 파싱된 배열만 다루므로 이 축은
    벡터가 아니라 여기서 고정된다."""
    toks, refused = transfer_plan._zone_tokens('["MID1","MID3"]')
    assert toks == ["MID1", "MID3"] and refused == []
    # 로트 이름에 쉼표가 든 경우도 JSON이면 안전하다.
    assert transfer_plan._zone_tokens('["A,B_01"]')[0] == ["A,B_01"]
    # JSON이 아니면 사람이 손으로 적은 텍스트다 — 클라와 같은 줄바꿈/쉼표 분해로 물러선다.
    assert transfer_plan._zone_tokens("MID1\nMID3")[0] == ["MID1", "MID3"]
    assert transfer_plan._zone_tokens("MID1, MID3")[0] == ["MID1", "MID3"]


def test_non_string_zone_element_is_refused_not_stringified():
    """숫자·bool을 문자열화하면 `True`/`true`, `42.0`/`42`로 양쪽이 갈린다. 패널은 그런
    값을 만들지 않으므로 흉내 낼 대상이 없다 — 옳은 답은 '읽을 수 없다'이다."""
    toks, refused = transfer_plan._zone_tokens('["MID1", 42, true]')
    assert toks == ["MID1"]
    assert refused == [42, True]


@pytest.mark.parametrize("raw", ["", "   ", None, "[]"])
def test_empty_zone_column_is_empty_not_a_refusal(raw):
    assert transfer_plan._zone_tokens(raw) == ([], [])

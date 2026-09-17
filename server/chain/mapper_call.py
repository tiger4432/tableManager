# -*- coding: utf-8 -*-
"""맵퍼를 «부르는 자리» — 워커와 재생이 같이 읽는다 (S-214, 판정 370).

🔴 실행기는 «하나»였고, 집이 틀렸습니다. `execute_custom_mapper` 는 저장소에 «한 벌»이고
   그 docstring 이 스스로 「모든 커스텀 맵퍼가 지나는 유일한 자리」라 적습니다. 그런데 그것이
   «워커의 집»에 살아서, 재생이 맵퍼를 돌리려면 워커를 import 해야 했습니다.
   -> 「한 실행기가 둘로 쪼개졌다」가 아니라 「공용 프리미티브가 한 호출자의 집에 산다」입니다.

🔴 S-211 ① 의 `withdraw_source` 와 «같은 기제, 반대 방향»입니다. 그때는 철회가 재생의 집에
   살면서 실행기가 그것을 썼고, 여기서는 맵퍼 실행이 워커의 집에 살면서 재생이 그것을 씁니다.
   처방도 같습니다: 둘보다 «아래»로.

⚠️ 트랜잭션은 여기 없습니다. 재생의 «청크 커밋»과 워커의 «그룹 트랜잭션»은 이 실행기 «밖»의
   성질이고, 이동이 그것을 건드리지 않습니다 — 옮긴 것은 「맵퍼를 어떻게 부르나」뿐입니다.
"""
import contextlib
import inspect
import math

import numpy as np
import pandas as pd

from maps import alignment_batch_counts

#: 🔴 [판정 498 ③] THE STAGE STAYS, THE TAG DOES NOT. `alignment_batch_counts` wants to
#: know how much of a group's wall clock the mapper took, and that is a fact about the call
#: rather than about the door - so the seat opens it. `LOG_FILENAME`, `MAPPER_LOG_TAG` and
#: this module's logger left with `execute_custom_mapper`: they were the SECOND execution
#: vocabulary, and an operator grepping 「did this rule run」 had to know the kind before they
#: could pick the words.
@contextlib.contextmanager
def stage_timing():
    """Time the mapper call the way the group line reports it."""
    with alignment_batch_counts.stage("mapper"):
        yield


def mapper_accepts_rule(mapper_func) -> bool:
    """맵퍼 함수가 선택적 `rule` 키워드 인자를 받는지 판정한다(기존 맵퍼 하위호환 유지)."""
    try:
        sig = inspect.signature(mapper_func)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if "rule" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

def without_missing(value):
    """`_missing_as_none` without the flag - the shape the call sites want."""
    return _missing_as_none(value)[0]

def result_row_count(result):
    """How many rows the mapper produced, counted across the shapes a mapper returns.

    Counted rather than assumed. A mapper returns `{"updates": [...]}`, or
    `{"batches": [{"updates": [...]}, ...]}`, and either may also carry
    `map_metadata_updates` - the three shapes are all in production today. A number
    that read only the first would report 0 for a mapper that did a map's worth of
    work, and "0" is the answer the operator is trying to tell apart from "did not
    run".
    """
    if not isinstance(result, dict):
        return 0
    total = len(result.get("updates") or ())
    for batch in result.get("batches") or ():
        if isinstance(batch, dict):
            total += len(batch.get("updates") or ())
    total += len(result.get("map_metadata_updates") or ())
    return total

def _is_missing_scalar(value) -> bool:
    """Is this ONE value a missing marker? Same rule as `parsers/pipeline_base.py:73-75`.

    🔴 THE SPELLING IS COPIED FROM THERE ON PURPOSE, INCLUDING `inf`. That file already
    decided what "no value" means when a frame becomes rows - `pd.isna` for None/NaN/NaT,
    and a second clause turning float infinities into None as well - and the mapper
    boundary is the same decision in a third place, not a new one. If these two ever
    disagree, the same source value becomes a number on one path and a blank on the other.

    ⚠️ `pd.isna` ANSWERS ELEMENTWISE FOR CONTAINERS, so a DataFrame or an ndarray comes
    back as an array of booleans rather than one. Those are not scalars and are left
    alone; taking their truth value here would raise, which is how this kind of guard
    usually fails - loudly, on the one payload shape nobody tested.
    """
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    try:
        answer = pd.isna(value)
    except (TypeError, ValueError):                      # unhashable / odd objects
        return False
    return bool(answer) if isinstance(answer, (bool, np.bool_)) else False


def _missing_as_none(value):
    """Deep-replace missing markers with `None`. Returns `(value, changed)`.

    🔴 UNCHANGED INPUT COMES BACK AS THE SAME OBJECT, not a rebuilt copy. A payload with
    no missing value in it must pass through byte-identical: a normaliser that quietly
    rewrites healthy values is a silent regression, and one that copies every payload
    would also make every mapper's `is` comparison and every large batch pay for a defect
    that was not there.
    """
    if isinstance(value, dict):
        changed = False
        rebuilt = {}
        for key, item in value.items():
            new_item, item_changed = _missing_as_none(item)
            rebuilt[key] = new_item
            changed = changed or item_changed
        return (rebuilt, True) if changed else (value, False)

    if isinstance(value, (list, tuple)):
        changed = False
        rebuilt = []
        for item in value:
            new_item, item_changed = _missing_as_none(item)
            rebuilt.append(new_item)
            changed = changed or item_changed
        if not changed:
            return value, False
        return (tuple(rebuilt) if isinstance(value, tuple) else rebuilt), True

    if value is None:
        return value, False                              # already missing; nothing to do
    if _is_missing_scalar(value):
        return None, True
    return value, False

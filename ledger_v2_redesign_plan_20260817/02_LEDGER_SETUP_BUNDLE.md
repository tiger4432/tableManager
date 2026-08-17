# 2단계 — 모듈형 Config Directory와 단일 Logical LedgerSetupBundle 계약

> 실행 상태: `COMPLETE` · 승인: `APPROVED` · 2026-08-17 사용자 승인
> 구현 근거: [`STAGE_2_ACCEPTANCE_EVIDENCE.md`](./STAGE_2_ACCEPTANCE_EVIDENCE.md)

## 목표

Ledger 작성자가 편집하는 정본을 `server/config/ontology/` 한 루트로 모은다. Pack/Profile과
모든 Registry section은 `ledger_config.json` 한 파일에 함께 두고, 물리 catalog와 dataflow만
분리한다. loader는 `manifest.json`에서 시작해 하나의 logical `LedgerSetupBundle`로
정규화한다. 이 단계는 schema·normalization·validation만 구현하며 runtime/DB는 실행하지 않는다.

v2에는 Position section이나 position Role이 없다. 좌표는 stage-local Entity의 identity key로
표현하고, 이동은 source Entity에서 target Entity로 향하는 Claim이다.

## 물리 파일 계약

정본 디렉터리와 각 파일 역할은 `CONFIG_CANON.md`가 소유한다. 최소 manifest:

```jsonc
{
  "setup_version": 2,
  "ledger": "ledger_config.json",
  "catalog": {
    "tables": "catalog/tables.json",
    "virtual_joins": "catalog/virtual_joins.json"
  },
  "dataflows": {
    "chains": "dataflows/chains.json",
    "enrichments": "dataflows/enrichments.json"
  }
}
```

경로는 `server/config/ontology/` 아래의 정규 상대경로만 허용한다. `..`, 절대경로, symlink
escape, glob, 미등재 파일 자동 발견을 금지한다.

## 정규화된 Logical Bundle 계약

```jsonc
{
  "setup_version": 2,
  "tables": {},
  "virtual_joins": {},
  "vocabulary": {},
  "entities": {},
  "source_preparers": {},
  "mappers": {},
  "packs": {},
  "profiles": {},
  "sources": {},
  "chains": {},
  "enrichments": {}
}
```

각 물리 파일은 자기 section만 소유한다. loader가 합친 뒤 위 logical 모양으로 validator에
전달한다. Registry 내용은 config에서만 오며 code builtin과 병합하지 않는다.

## 정규화 예시

```jsonc
{
  "setup_version": 2,
  "vocabulary": {
    "transferred_to@1": {
      "status": "active",
      "layer": "ontology",
      "subjects": ["CoreDie@1", "DTDie@1"],
      "object": {
        "kind": "entity_ref",
        "types": ["DTDie@1", "BondComponent@1"]
      }
    }
  },
  "entities": {
    "CoreDie@1": {"keys": ["core_wafer", "core_x", "core_y"]},
    "DTDie@1": {"keys": ["dt_lot", "dt_slot", "dt_x", "dt_y"]},
    "BondComponent@1": {
      "keys": ["bond_wafer", "bond_x", "bond_y", "layer"]
    }
  },
  "source_preparers": {
    "dt-transfer-frame@1": {
      "implementation_id": "dt-transfer-frame",
      "implementation_version": 1,
      "input_columns": ["dt_job_id", "b_wx", "b_wy"],
      "output_columns": {
        "inventory_dt_lot": "string",
        "inventory_dt_slot": "number",
        "resolved_dt_x": "number",
        "resolved_dt_y": "number"
      },
      "accepts_verified_join_rules": true
    }
  },
  "mappers": {
    "dt-transfer@1": {
      "implementation_id": "dt-transfer-role",
      "implementation_version": 1,
      "unit": {"kind": "event"},
      "input_columns": [
        "core_wafer_id", "core_x", "core_y",
        "inventory_dt_lot", "inventory_dt_slot",
        "resolved_dt_x", "resolved_dt_y", "event_time", "dt_job_id"
      ],
      "emits": ["transfer@1/movement"]
    }
  },
  "packs": {
    "transfer@1": {
      "claims": {
        "movement": {
          "roles": {
            "subject": {"kind": "entity", "required": true},
            "target": {"kind": "entity", "required": true},
            "occurred_at": {"kind": "time", "required": true},
            "event_key": {"kind": "identity", "required": false},
            "qty": {"kind": "quantity", "required": false}
          },
          "emit": {
            "predicate": "transferred_to@1",
            "subject": "$subject",
            "object": {
              "kind": "entity_ref",
              "entity": "$target",
              "qualifiers": {
                "event_key": "$event_key?",
                "qty": "$qty?"
              }
            },
            "occurred_at": "$occurred_at"
          }
        }
      }
    }
  },
  "profiles": {
    "dt-transfer@1": {
      "source": "dt_log",
      "packs": ["transfer@1"],
      "mappings": [{
        "mapping_id": "movement",
        "use": "transfer@1/movement",
        "bind": {
          "subject": {
            "kind": "entity",
            "entity_type": "CoreDie@1",
            "keys": {
              "core_wafer": {"kind": "column", "column": "core_wafer_id"},
              "core_x": {"kind": "column", "column": "core_x"},
              "core_y": {"kind": "column", "column": "core_y"}
            }
          },
          "target": {
            "kind": "entity",
            "entity_type": "DTDie@1",
            "keys": {
              "dt_lot": {"kind": "column", "column": "inventory_dt_lot"},
              "dt_slot": {"kind": "column", "column": "inventory_dt_slot"},
              "dt_x": {"kind": "column", "column": "resolved_dt_x"},
              "dt_y": {"kind": "column", "column": "resolved_dt_y"}
            }
          },
          "occurred_at": {"kind": "column", "column": "event_time"},
          "event_key": {"kind": "column", "column": "dt_job_id"}
        }
      }]
    }
  },
  "sources": {
    "dt_log": {
      "relation": "dt_log",
      "driver": {
        "unit": "group",
        "identity": ["dt_job_id"],
        "group_by": ["dt_job_id"],
        "order_by": ["row_identity"],
        "occurred_at": {"column": "event_time", "timezone": "Asia/Seoul"},
        "cursor": {"columns": ["event_time", "row_identity"]},
        "preparation": {
          "preparer_id": "dt-transfer-frame@1",
          "inherit_virtual_join_rules": ["dt_log_to_dt_inventory"]
        },
        "mapper_id": "dt-transfer@1"
      },
      "profile_id": "dt-transfer@1"
    }
  }
}
```

위 `inventory_dt_lot/inventory_dt_slot/resolved_dt_x/resolved_dt_y`는 cursor가 virtual column을
직접 읽는다는 뜻이 아니다.
cursor는 `dt_log`의 물리 컬럼과 watermark만 읽는다. 등록된 source preparer가 그 배치를
관련 relation과 한 번에 join하여 이 열이 포함된 EventFrame을 반환하고, Profile은 그
완성 열만 참조한다. join key·오른쪽 row·preparer version은 EventFrame provenance에 남긴다.
`lookups` section이나 `declared_lookup` binding은 unknown field/kind로 거절한다.

Mapper의 공통 실행은 `BaseLedgerMapper.map()`이 소유하고 최종 출력은 pandas RoleFrame이다.
개별 Python 구현은 준비된 unit을 `RoleEmission`으로 해석하는 훅만 제공한다. config의
`implementation_id`는 trusted class registry를 선택하지만 module/function/path를 실행하지
않는다. 상세 계약은 [`MAPPER_DESIGN_PATTERN.md`](./MAPPER_DESIGN_PATTERN.md)가 정본이다.

`inherit_virtual_join_rules`는 rule ID만 적는다. `left_table`, `right_table`, `join_key`,
`expose`, notation folding, `join_cardinality`, UNIQUE 승인 근거는
`catalog/virtual_joins.json`과 그 verified compiler가 단독 소유한다. LedgerSetupBundle에 같은
키를 다시 적으면 중복 선언으로 거절한다.

기존 virtual join의 UI용 absent-only 병합은 상속하지 않는다. source preparer는 오른쪽 값을
`inventory_*`처럼 충돌 없는 output column으로 보존한다. 기록된 `dt_log.dt_lot`이 틀린 경우
그 값이 inventory 확정값을 이기는 사고를 막기 위해서다. UI용 `unresolved_label`, 셀 source
표시도 Ledger EventFrame에 넣지 않는다.

실제 Binding에는 기존 `binding_origin`, `approval_status`, 선택적 `suggestion_reason`이
정규화되어 보존된다. 위 예시는 구조 설명을 위해 승인 metadata를 생략했다.

좌표가 없는 bulk 이동은 별도 Position을 만들지 않고 `CoreWafer`, `DTJob`, `DTSlot` 같은
container/collection Entity를 subject/target으로 사용한다. 다이 대응이 생기면 더 정밀한
stage-local Entity 사이의 Claim을 추가한다.

## validator 범위

- root/section version
- manifest file list, root confinement, duplicate/unlisted file
- ID와 version 문법
- 중복 ID와 reference 존재 여부
- cursor relation/column의 table_config 존재 여부
- source preparer가 선언한 EventFrame output schema와 Profile column의 일치
- 상속 virtual join rule ID 존재·enabled·verified·left relation 일치
- source preparer가 join key/expose/folding을 중복 선언하면 거절
- timezone 명시
- identity/group/order/cursor의 빈 목록·불일치
- Entity exact identity keys
- Pack claim/role/binding 구조
- Pack emission의 subject/target과 Vocabulary entity_ref 계약
- approval metadata와 readiness 분리
- 임의 field/expression/module/path 금지
- 결정적 오류 정렬과 직렬화
- Registry entry가 config 밖 Python builtin에만 존재하지 않는다는 검사

## 전용 오류 최소 목록

```text
unsupported_setup_version
unknown_relation
unknown_column
unknown_entity_type
unknown_predicate
unknown_pack
unknown_claim
unknown_role
missing_required_role
invalid_entity_ref
invalid_binding
invalid_driver
invalid_cursor
invalid_timezone
duplicate_id
unsafe_declaration
binding_not_approved
```

각 오류는 `code/path/message`를 포함한다.

## 수락 테스트

- 같은 Bundle의 결정적 normalization/serialization
- 같은 manifest/files의 결정적 normalization/serialization
- manifest 배열 순서는 보존하되 section JSON key 순서에는 독립
- glob/미등재 파일/root escape/중복 ID 거절
- section/key 순서를 바꿔도 동일 snapshot input
- source/column을 전부 바꾼 동일 Pack Profile 검증
- table_config에 없는 relation/column 거절
- Entity missing/extra/wrong key 거절
- Pack/Vocabulary subject/object type 불일치 거절
- unsupported version과 unknown reference 전용 오류
- pending/rejected는 구조 검증 통과, readiness 실패
- 공통 schema/validator에 DT/Bonding/Core/source 이름 비참조
- Position/Frame section을 넣으면 unknown field로 거절
- `lookups` section과 `declared_lookup` binding 거절
- validator/compiler DB read 0
- virtual join rule 변경이 snapshot hash에 반영
- compiler/runtime/DB migration/write 0

2단계는 사용자 승인을 받아 `ac380e4`까지 `main`에 fast-forward 병합됐다.

## 현재 구현 상태

순수 authoring 경계와 strict manifest loader는 `server/ledger/setup_bundle.py`에 구현했다.
운영 JSON은 아직 만들지 않았고 runtime loader에도 연결하지 않았다. `chains`와
`enrichments`의 개별 실행 문법, 물리 UNIQUE 실측, Registry snapshot은 다음 승인 단계의
소유이므로 이 단계에서는 객체/금지 실행 키만 검사한다. DB read/write, migration, compiler,
translator, cursor 변경은 없다.

재승인 보완으로 malformed descriptor는 semantic lookup 전에 구조 오류로 닫히며, 모든
Vocabulary/Pack과 미사용 Profile/Mapper도 전수 교차 검증한다. Pack emission Role의 실재·kind,
Profile packs/mapping/Mapper emits, Mapper/Profile/Preparer 열, Source unit/group, catalog
key/index와 선언된 exact UNIQUE 근거가 자동 반례로 고정됐다. 물리 DB에서 그 UNIQUE가 실제로
존재하는지 확인하는 일만 후속 단계에 남는다.

f03b165 후속 보완에서는 미사용 Profile도 `Profile.source`의 physical relation과 Preparer
EventFrame schema로 entity/leaf column을 검사하도록 선택 Profile과 같은 검증 경로에 합쳤다.
`order_by`와 `cursor.columns`는 각각 catalog의 business/composite/UNIQUE index 전체 열로
동률 제거를 증명해야 하며, non-unique index나 identity 자체는 근거가 아니다. `chains`와
`enrichments`의 금지 실행 키는 중첩 JSON 배열을 포함해 완전 탐색하고, Entity `key_types`의
각 값은 trimmed non-blank string으로 닫았다. 이 변경은 순수 validator와 테스트뿐이었다.
Registry/snapshot은 승인된 3단계 범위에서 별도 모듈로 구현했다. RoleFrame, Pack compiler,
source row/runtime/DB/cursor 실행 연결은 여전히 후속 단계다.

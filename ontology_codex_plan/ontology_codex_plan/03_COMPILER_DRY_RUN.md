# 3단계 — Compiler, adapter, dry-run

`COMMON_ARCHITECTURE_RULES.md`와 이전 단계 수락 테스트를 적용하고 3단계만 수행하라.

## 목표

검증된 Profile을 기존 `lot_event` 및 transfer translator 런타임 설정으로 결정적으로 컴파일한다. 기존 translator를 복제하지 않는다.

## 구현

- `TemplateRegistry`
- `CompilerRegistry`
- `SourceAdapterRegistry`
- `LotLineageTemplateCompiler`
- `TransferTemplateCompiler`
- 기존 runtime config adapter
- dry-run 서비스
- 샘플 행의 업무 문장 preview
- molecule 및 생성 예정 atom preview

source 이름은 compiler 조건문이 아니라 adapter 등록값으로 처리한다.

## Parity 검증

```text
기존 수동 config → 기존 translator → atoms
Profile → compiler/adapter → 기존 translator → atoms
```

다음이 의미상 동일해야 한다.

- subject type/keys
- predicate
- object kind/payload
- occurred_at
- source
- translator derivation
- raw reference
- refusal/incomplete 결과

등록 상태 때문에 byte equality가 불가능하면 semantic normalization 기준을 문서화하고 테스트로 고정한다.

Dry-run은 DB에 쓰지 않는다. 실제 적용 API와 UI는 만들지 않는다. 완료 후 parity 결과와 모든 회귀 테스트를 보고한다.


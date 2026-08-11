# 확정 문장이 두 값 가정을 버렸다 — 같은 모양이 두 번째 자리에 또 쓰여 있었다

**날짜:** 2026-08-11 16:40 · **커밋:** `42d7600` · **레인:** 클라(map2)
**측정 상자:** 이 워크스테이션. 라이브 서버에 arity 1·3 규칙을 태운 적은 없다(아래 참조).

---

## 배경

`3d43a6c`가 `keyFrom`에서 지운 것은 **두 값 모양**이었다. 그런데 같은 모양이
`map_editor2.html:856`에 **두 번째로 쓰여 있었다** — `data-me2-confirm-eqp`와
`-product`라는 훅 두 개, 그리고 그것을 이름 붙은 필드 둘로 먹이는 뷰 모델.

운영 규칙은 컬럼을 **하나** 선언한다. 사용자가 읽은 확정 문장은 **자기 규칙에 없는
모양으로 조립된 문장**이었다.

## 무엇을 했나

슬롯 하나(`data-me2-confirm-unit`)로 줄이고, 서버가 만든 `__key` dict를 그대로 읽는
합성기를 넣었다. **키 순서가 곧 선언이고 길이가 곧 arity**라, 이 함수 안의 어느 갈래도
arity를 구별하지 못한다.

```javascript
export function unitValuesOf(decision) {
  const d = decision && typeof decision === 'object' ? decision : {};
  const served = d.__key && typeof d.__key === 'object' ? d.__key : null;
  const source = served ? Object.keys(served).map(col => own(served, col)) : [d.eqp, d.product];
  const out = [];
  for (const raw of source) {
    const value = firstStated(raw);
    if (value !== null) out.push(value);
  }
  return out;
}
```

뷰 모델 레코드에서 **`eqp`·`product` 두 필드가 사라진 것이 변경의 요점**이다. 이름 붙은
필드 둘이 곧 두 값 모양이었다 — arity 1이면 `product`가 비어 구분자가 허공에 남고,
arity 3이면 셋째 값이 화면에 아무 말 없이 사라졌다.

구분자는 발명하지 않았다. 이 화면이 이미 `note`·`metaLine`·`referenceOptionLabel`에서
쓰던 것에 `UNIT_SEPARATOR`라는 이름만 붙였다 — 한 화면에 조인 문자가 둘이면 독자는 그
둘이 다른 뜻이라고 배운다.

### 하네스 단언이 **잘못된 것을 고정**하고 있었다

`map_editor2_shell_harness.mjs:483`이 `confirm.eqp === 'E1'`과
`confirm.product === 'P1'`을 단언하고 있었다. 그 두 줄이 두 값 모양을 **계약으로 붙들고
있었다 — 핀 자체가 결함이었다.** 삭제가 아니라 교체했고, arity 1·3과 셸이 실제로 쓴
문장의 DOM 읽기, 마크업 훅 인구조사까지 확장했다.

변이 검사가 왜 양쪽 절반이 다 필요한지 말한다: **단위를 두 값으로 자르면 — 정확히
은퇴한 그 모양을 복원하면 — 모든 arity-2 단언이 초록으로 남는다.** arity-3 줄과 음성
대조에서만 죽는다. `3d43a6c`의 교훈이 같은 주에 반복된 것이다 — **arity 2만 도는
테스트는 이미 되던 상태를 테스트한다.**

## 아키텍처 영향

- 결정키 컬럼 이름이 클라 소스에 **한 자리도 남지 않는다.** 문장은 값만 쓰고 축 이름은
  옆 패널이 이미 말한다.
- 복잡도 예산: 슬롯 하나 제거, 추가 0. **순 −1.** 쓰기는 여전히 동작 하나이고 주어를
  한 번만 이름 댄다.

## 검증 (커밋이 기록한 수치)

- shell harness **577 → 594 ran, 0 failed**, 바닥값을 같은 변경에서 올림.
- 총 어서션 **26,426 → 26,443**, KNOWN_RED **5** 불변.
- `check:contracts` 7/7 불일치 없음, `check:harnesses` 44 초록.
- prebuild + build 종료코드 0.
- 변이 7건 전부 사망, 7건 전부 자기 어서션 줄을 인쇄. 그중 둘은 각각 **인구조사에서만**,
  **DOM 절에서만** 잡혔다.
- 🔴 내가 직접 확인한 것: 이 커밋 이후 `client2/map_editor2.html` 소스에 은퇴한 두 훅이
  **0회** 나타난다. (빌드 산출물의 번들 파일명은 다음 빌드에 바뀌므로 적지 않는다.)

## 그때 남아 있던 것

- 문장과 전송되는 키가 **둘 다 `__key`에서 오지만 서로 다른 함수를 통과한다.** 채택된
  규칙이 선언하지 않은 컬럼을 서버가 실어 보내면 **보여진 뒤 버려진다.** 규칙 전환을
  견디는 결정이 필요해 이 라운드에서 채점하지 않았다.
- 레거시 위치 브리지(`__key`가 서빙되지 않을 때)는 여전히 **둘에서 멈춘다.**
- **arity 1·3 규칙을 라이브 서버에 태운 적이 없고, 확정 버튼을 누른 적이 없다.**
- `docs/architecture/frontend.md:8`은 이 커밋 시점에 「이 문장은 두 키 값을 가정한다」고
  적고 은퇴한 훅 둘을 이름 대고 있다 — **두 절 다 이 커밋 기준 거짓**이며, 이 커밋은
  그것을 고치지 않았다(문서 소관).
</content>

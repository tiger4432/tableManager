# §13 선언 진단 — 실행 결과 (응용 기획 세션, 2026-08-21)

**원장 없이 · 숫자 없이 · kind 하드코딩 없이 돌아간 첫 실물.**
`ontology_application_algorithm.md` §13 의 실행판. 입력은 `server/config/mechanism_models.json`
하나뿐이고 DB 를 안 본다.

---

## 실행 방식 — 일반화를 «같이» 실증한다

    kind 를 이름으로 부르지 않는다   선언에서 `role: "formation"` 인 모델을 «전부» 열거
    씨앗                            각 모델의 `target`
    전파                            상류로, 분기에서만 나뉨 (감쇠 상수 0개)
    산출                            뿌리 원인 × 활성 × 경로수 × bindings 교차

🔴 **셋째 kind 가 선언되면 코드 0줄로 같이 나온다.** 그것이 이 실행의 수락 단언이다.

---

## 결과 ① `void_formation` (finding_kind = void)

    뿌리 원인                  활성      경로수   잴 수 있나
    bond_pressure            0.1429    1       O    최상위
    core_cmp_nonuniform      0.1429    1       X    최상위
    dt_pass_count            0.1429    1       X    최상위
    humidity                 0.1429    1       X    최상위
    stage_particle           0.1429    1       X    최상위
    tape_adhesion_anomaly    0.1429    1       X    최상위
    bond_temp                0.0714    1       O
    pre_bond_queue_h         0.0714    1       X

    candidate    최상위 6개, 동률 — 선언상 아직 안 갈린다
    왜 안 갈리나  그중 5개는 «잴 방법이 없다». 데이터가 쌓여도 영원히 안 갈린다
    ▶ action     그 다섯 중 하나의 «측정을 시작»하라

## 결과 ② `delam_formation` (finding_kind = delam)

    backside_damage          0.5000    1       X    최상위
    bond_pressure            0.5000    1       O    최상위
    tape_adhesion_anomaly    0.0000    0       X    🔴 아래 참조

    candidate    최상위 2개, 동률
    ▶ action     `backside_damage` 의 측정을 시작하라

---

## 🔴 첫 실행이 «선언 결함»을 하나 잡았다

    delam_formation
      nodes   bond_pressure · die_stress · tape_adhesion_anomaly · backside_damage · delam
      edges   bond_pressure -> die_stress -> delam
              backside_damage -> delam
              🔴 tape_adhesion_anomaly 에서 «나가는 엣지가 없다»

`tape_adhesion_anomaly` 는 **노드로 선언됐는데 `delam` 에 닿는 경로가 없다.**
원인으로 적어 놓고 엣지를 안 그렸다.

**사람이 읽어서는 안 보인다** — 노드 목록에 이름이 있으니 「선언돼 있다」로 읽힌다.
전파가 «활성 0 · 경로 0» 을 내면서 드러났다.

⚠️ **기전 선언은 이 세션 소관이 아니다.** 사실만 넘긴다 — 엣지를 빠뜨린 것인지,
의도적으로 `void` 쪽에만 연결한 것인지는 선언 소유자가 안다.
(`void_formation` 에는 `tape_adhesion_anomaly -> backside_damage` 엣지가 있다.)

---

## 이 실행이 증명한 것 셋

    ① kind 하드코딩 0        void·delam 을 이름으로 안 불렀다. 셋째가 오면 자동
    ② 사람이 해석할 게 없다   출력이 「후보 + 왜 안 갈리나 + 무엇을 하라」.
                            관문 ✓✗ 를 읽고 «합성하는 단계»가 없다 — A 판정 만족
    ③ 숫자를 안 낸다         활성은 «동률 판정»에만 쓰이고, 나가는 것은 「최상위 6개, 동률」.
                            경로 수는 상수 없는 정수 계수(§19.2, DAG 전용)

## 그리고 응용 ⑤ 가 «부산물»로 나왔다

`ontology_application_algorithm.md` §12 는 「⑤ 죽은 선언 찾기」를 별도 응용으로 적었다.
**별도로 만들 필요가 없다** — 같은 전파가 활성 0 을 내면서 잡는다.
§12-⑤ 는 독립 응용이 아니라 ① 의 부산물로 내려간다.

---

## 한계 — 정직하게

    선언에 «대한» 진단이다      어느 랏에 대한 진단이 아니다. 인스턴스 질문은 원장이 필요
    활성이 거의 동률인 이유      기전 그래프가 «트리»다 (19노드 18엣지 = n−1).
                              한 원인이 결과로 가는 길이 하나씩뿐이라 갈릴 수가 없다
                              -> 편차는 «가지를 늘려야» 생긴다 (§22.2-⑤ 「비대칭에서만」)
    bindings 5건               측정 가능한 물리량이 셋뿐이다
                              (bond_pressure · bond_temp · post_bond_queue_h)

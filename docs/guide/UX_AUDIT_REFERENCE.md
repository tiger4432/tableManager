# UX 감사 참조 — 업계 통념 (2026-09-16 신설, 소유자 「사회적이나 업계 통념」)

> 🔴 **순위가 있습니다.** ① 저장소 자기 시스템(`.claude/skills/ui-design-system/SKILL.md` + 캐논 `client2/src/ontology_explorer.css`) → ② `CLAUDE.md` 의 UI 상설 넷 → ③ **이 문서**.
> ③ 은 ①② 가 «말 안 하는» 자리에서만 씁니다. 문제에 «이름을 붙이는» 용도이지 ①② 를 «덮는» 용도가 아닙니다.
> 📎 이 제품의 사용자는 «로그를 못 읽는 도메인 운영자»입니다. 그래서 아래에서도 «복잡한 도구» 판을 정본으로 씁니다.

## A. Nielsen 10 heuristics — 그중 «복잡한 도구»에 대한 해설 (NN/g)
```
①  시스템 상태가 «보인다»     10초 넘는 작업은 «단계와 남은 것»을 보인다. 「잠시만 기다려 주세요」는 부족하다
②  현실의 말을 쓴다          그 분야의 «도메인 낱말»로. 관행을 깨면 «자주 쓰는 사람»도 계속 헷갈린다
③  사용자가 «되돌릴» 수 있다   되돌리기·복원. 이력이 있어야 «해 보면서 배우는 것»이 안전해진다
④  일관성                   작업공간 전부에서 «같은 말·같은 모양». 안(제품)과 밖(업계 관행) 둘 다
⑤  실수를 «막는다»           값을 바꾸는 동안 «미리보기»로 효과를 즉시 보인다
⑥  외우게 하지 않는다        식별자 옆에 «알아볼 수 있는 것»을 같이 (번호 옆에 그림)
⑦  숙련자용 가속            단축키 등 — 숙련자가 «효율 정체»를 넘게
⑧  미니멀                   고급 설정은 «단계적으로» 숨기고, 중복·장식은 «뺀다»
⑨  오류를 «알아보고 고치게»   무엇이 문제인지 «구체적»으로 + 해결의 «다음 행동». 못 담으면 문서로 링크
⑩  도움말은 «그 자리»에      화면 안 도움말. 밖의 문서는 «안 봅니다»
```
🔵 **①⑨ 가 이 제품의 급소입니다** — 운영자가 로그를 못 읽으니, 「지금 무엇이 도나」와 「무엇이 왜 막혔고 다음에 뭘 하나」는 «화면 말고 답할 자리가 없습니다».

## B. Shneiderman 8 golden rules (1985/1986, 「Designing the User Interface」)
```
① 일관성  ② 숙련자용 지름길  ③ 모든 행동에 «되먹임»  ④ 작업의 «닫힘»(끝났다는 표시)
⑤ 오류를 막고, 나면 «회복법»을 준다   ⑥ 되돌리기  ⑦ 사용자가 «주도»한다(제품이 아니라)
⑧ 기억 부담 최소 — 한 화면의 것을 외워서 «다른 화면»에 쓰게 하지 않는다
```
⚠️ ③④ 가 A① 과 겹칩니다. 겹치는 것은 «더 강한 증거»이지 중복이 아닙니다.

## C. 이 저장소에서 «이미» 판정된 것과의 관계 — 새 규칙이 아닙니다
```
A⑨ = CLAUDE.md 「거절의 «사유»와 «다음 행동»은 남는다」   (자막 단 실패도 실패다)
A⑧ = CLAUDE.md 「설명 문구 주저리주저리 금지」            (「지우면 틀리게 읽나」)
A② = CLAUDE.md 「번역체 금지 — 기호·짧은 영어·명사형」 · 「도메인은 사용자가 적는다」
A⑥ = CLAUDE.md 「사람이 기억해야 하는 절차는 구멍이다」
B⑧ = 같은 줄
🔴 즉 업계 통념의 «대부분»이 이미 이 저장소에 «자기 말»로 적혀 있습니다.
   이 문서의 값은 «빠진 것»을 찾는 데 있습니다 — 특히 A①(단계와 남은 것) · A③/B⑥(되돌리기) ·
   A⑦(숙련자 가속) · A⑩(그 자리 도움말)은 CLAUDE.md 에 대응 문장이 «없습니다»
```

## 출처
- [10 Usability Heuristics for User Interface Design — NN/g](https://www.nngroup.com/articles/ten-usability-heuristics/)
- [10 Usability Heuristics Applied to Complex Applications — NN/g](https://www.nngroup.com/articles/usability-heuristics-complex-applications/)
- [Shneiderman's Eight Golden Rules — IxDF](https://ixdf.org/literature/article/shneiderman-s-eight-golden-rules-will-help-you-design-better-interfaces)

# 2026-07-19 19:03:00 - 격자 맵 에디터 내 웨이퍼 원안에 완전히 들어오는 셀 하이라이트(Wafer Circle Completely-Inside Cell Highlight) 구현

## 1. 개요 및 동기
* **요구사항**: 웨이퍼 경계선에 단순히 걸치는 셀이 아니라, **웨이퍼 원(Circle) 안에 네 모서리가 완전히 포함(Completely Inside)되는 칩(셀)들만** 밝은 녹색(Neon Green)으로 하이라이트 표시하도록 필터를 수정해달라는 요청이 있었습니다.
* **해결 방안**: 
  * visual cell $(c, r)$의 가장 먼 모서리와 원 중심 사이의 거리 제곱($d_{max}^2$)을 계산합니다.
  * $d_{max}^2 \le 1.0$ 조건을 충족하는 셀(즉, 셀 전체 면적이 원판 테두리 내부에 완벽히 포함되는 칩)에 대해서만 `.cell-inside-wafer` 클래스를 부여하고 밝은 네온 녹색으로 시각화했습니다.

---

## 2. 주요 구현 사항

### A. 기하학적 내접 판단 알고리즘 (`client2/src/map_editor.js`)
```javascript
      // Check if visual cell (c, r) is completely inside the wafer boundary circle
      const u1 = (2 * c - visualCols) / visualCols;
      const u2 = (2 * (c + 1) - visualCols) / visualCols;
      const v1 = (2 * r - visualRows) / visualRows;
      const v2 = (2 * (r + 1) - visualRows) / visualRows;

      const maxU2 = Math.max(u1 * u1, u2 * u2);
      const maxV2 = Math.max(v1 * v1, v2 * v2);
      const dMax2 = maxU2 + maxV2;

      const completelyInside = (dMax2 <= 1.0);

      if (completelyInside) {
        cell.classList.add('cell-inside-wafer');
      }
```

### B. Neon Green 하이라이트 스타일 구현 (`client2/src/style.css`)
```css
/* 웨이퍼 원안에 완전히 들어오는 격자 셀 하이라이트 */
.grid-cell.cell-inside-wafer {
  outline: 1.5px solid #22c55e !important; /* bright neon green outline */
  outline-offset: -1.5px;
  box-shadow: inset 0 0 6px rgba(34, 197, 94, 0.4);
}
.grid-cell.cell-inside-wafer:not(.has-value) {
  background: rgba(34, 197, 94, 0.08) !important;
}
```

---

## 3. 아키텍처 영향 보고
* **유효 칩(Die) 영역 식별 용이성**: 원형 라인을 넘나드는 경계선 칩을 제외하고, 물리적으로 원판 내에 100% 온전하게 존재하는 칩만 녹색 실선으로 뚜렷하게 도식화되므로 불량 유무 및 맵 데이터 매핑 영역 식별이 대폭 편리해졌습니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 완벽하게 마감되었습니다.

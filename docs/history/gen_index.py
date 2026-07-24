#!/usr/bin/env python3
"""
docs/history/README.md 인덱스 자동 생성기.

히스토리 파일명(YYYYMMDD_HHMMSS_summary.md 또는 YYYY-MM-DD_summary.md)에서
날짜와 제목을 파싱하여 연-월별로 그룹화한 최신순 인덱스를 생성한다.

사용법:
    python docs/history/gen_index.py         # README.md 갱신
    python docs/history/gen_index.py --check  # 변경 필요 여부만 검사(CI용, 종료코드 1=갱신필요)

거버넌스 규칙 #4(히스토리 인덱스 자동화)에 따라 README.md는 수동 편집하지 않는다.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

HISTORY_DIR = Path(__file__).resolve().parent
README = HISTORY_DIR / "README.md"

# 20260412_221000_...  또는  2026-04-15_...
DATE_RE = re.compile(r"^(?P<y>\d{4})[-_]?(?P<m>\d{2})[-_]?(?P<d>\d{2})(?:_(?P<time>\d{6}))?_(?P<slug>.+)$")

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}


def humanize(slug: str) -> str:
    """phase19_integrity_and_stability_fixes -> Phase19 Integrity And Stability Fixes"""
    words = slug.replace("-", "_").split("_")
    return " ".join(w[:1].upper() + w[1:] if w else w for w in words)


def collect() -> list[tuple[date, str, str, str]]:
    """(날짜, 시각문자열, 표시제목, 파일명) 리스트를 최신순으로 반환."""
    entries = []
    for path in HISTORY_DIR.glob("*.md"):
        if path.name == "README.md":
            continue
        stem = path.stem
        mo = DATE_RE.match(stem)
        if not mo:
            # 규격 외 파일명: 파싱 실패 목록으로 별도 처리
            entries.append((None, "", humanize(stem), path.name))
            continue
        y, m, d = int(mo["y"]), int(mo["m"]), int(mo["d"])
        try:
            dt = date(y, m, d)
        except ValueError:
            entries.append((None, "", humanize(stem), path.name))
            continue
        time = mo["time"] or ""
        hhmm = f"{time[:2]}:{time[2:4]}" if time else ""
        entries.append((dt, hhmm, humanize(mo["slug"]), path.name))
    # 최신 날짜 -> 오래된 날짜, 같은 날짜는 시각 역순
    entries.sort(key=lambda e: (e[0] or date.min, e[1]), reverse=True)
    return entries


def render(entries: list[tuple]) -> str:
    dated = [e for e in entries if e[0] is not None]
    undated = [e for e in entries if e[0] is None]

    lines = [
        "# 📜 AssyManager Project History Index",
        "",
        "> **자동 생성 문서 — 직접 편집 금지.** `python docs/history/gen_index.py`로 갱신하십시오.",
        f"> 총 **{len(dated) + len(undated)}개** 이력. (거버넌스 규칙 #4)",
        "",
        "각 파일은 `YYYYMMDD_HHMMSS_summary.md` 규격의 불변(append-only) 기술 이력입니다. "
        "아키텍처 전체 그림은 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)를 참조하십시오.",
        "",
    ]

    current_ym = None
    for dt, hhmm, title, fname in dated:
        ym = (dt.year, dt.month)
        if ym != current_ym:
            current_ym = ym
            lines.append("")
            lines.append(f"## {dt.year}-{dt.month:02d} ({MONTHS[dt.month]} {dt.year})")
            lines.append("")
        ts = f"{dt.year}-{dt.month:02d}-{dt.day:02d}" + (f" {hhmm}" if hhmm else "")
        lines.append(f"- **{ts}** — [{title}](./{fname})")

    if undated:
        lines.append("")
        lines.append("## 규격 외 파일명 (Unparsed)")
        lines.append("")
        for _, _, title, fname in undated:
            lines.append(f"- [{title}](./{fname})")

    lines.append("")
    lines.append(f"*Last generated: {date.today().isoformat()} by gen_index.py*")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    entries = collect()
    content = render(entries)
    check_only = "--check" in sys.argv
    existing = README.read_text(encoding="utf-8") if README.exists() else ""
    if check_only:
        if existing.strip() != content.strip():
            print("history/README.md is out of date. Run: python docs/history/gen_index.py")
            return 1
        print("history/README.md is up to date.")
        return 0
    README.write_text(content, encoding="utf-8")
    dated = sum(1 for e in entries if e[0] is not None)
    print(f"Wrote {README} ({dated} dated entries, {len(entries)} total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""[함수형 커스텀 파서] 이 파일의 계약은 **`parse_file(file_path) -> list[dict]` 함수 하나**다.

🔴 **이름이 "template"이지만 «둘 중 하나»일 뿐이다.** 인제션 파서에는 서로 다른 두 방식이 있고,
새 파서는 대개 **다른 쪽**에서 출발한다:

  * 이 파일 (함수형)     — 파일을 통째로 직접 읽어 dict 리스트를 만든다. pandas를 안 쓰거나
                           행/열 구조가 아닌 입력(매트릭스·이진·비정형)에 맞다.
  * `custom_parser.py.sample` (클래스형) — `BasePipelineParser`를 상속하고 `match()`와
                           `process_dataframe()` **둘만** 쓴다. 읽기·NaN 정리·DB 전달은 베이스가
                           한다. **표 형태 파일이면 거의 항상 이쪽이다.**
                           개발·검증·내보내기는 `server/parsers/notebooks/parser_workbench.ipynb`.
"""
import csv
import os

def parse_file(file_path: str) -> list[dict]:
    """
    사용자 커스텀 파서 예시: 2D 매트릭스 데이터를 XYZ 좌표계 테이블로 변환
    
    [Input Matrix Example]
    10, 20, 30
    40, 50, 60
    
    [Output list[dict] Example]
    [
      {"x": 0, "y": 0, "z": 10},
      {"x": 1, "y": 0, "z": 20},
      {"x": 2, "y": 0, "z": 30},
      {"x": 0, "y": 1, "z": 40},
      ...
    ]
    """
    rows_output = []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for y, row_data in enumerate(reader):
                for x, value in enumerate(row_data):
                    # 공백 제거 및 유효성 검사
                    val = value.strip()
                    if val:
                        rows_output.append({
                            "x": x,
                            "y": y,
                            "z": float(val) if val.replace('.','',1).isdigit() else val
                        })
        return rows_output
    except Exception as e:
        print(f"Error in custom parser: {e}")
        return []

if __name__ == "__main__":
    # 독립 테스트용 코드
    import sys
    if len(sys.argv) > 1:
        print(parse_file(sys.argv[1]))

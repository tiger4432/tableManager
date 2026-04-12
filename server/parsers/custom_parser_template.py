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

import pytest
from parsers.html_topology_parser import HTMLMatrixTableParser

def test_html_matrix_table_parsing():
    # 사용자가 제공해준 2D 매트릭스 테이블 구조의 HTML 소스
    html = """
    <table>
        <!-- 최상단 타이틀 행 -->
        <tr>
            <td colspan="12">AAA</td>
        </tr>
        <!-- 메타데이터 행 1 -->
        <tr>
            <td></td>
            <td rowspan="2">BDIE</td>
            <td colspan="2">LOT</td>
            <td colspan="2">A</td>
            <td colspan="2" rowspan="2">CDIE</td>
            <td colspan="2">LOT</td>
            <td colspan="2">C</td>
        </tr>
        <!-- 메타데이터 행 2 -->
        <tr>
            <td></td>
            <td colspan="2">WF</td>
            <td colspan="2">B</td>
            <td colspan="2">WF</td>
            <td colspan="2">D</td>
        </tr>
        <!-- X축 눈금 행 -->
        <tr>
            <td></td>
            <td>1</td>
            <td>2</td>
            <td>3</td>
            <td>4</td>
            <td>5</td>
            <td>6</td>
            <td>7</td>
            <td>8</td>
            <td>9</td>
            <td>10</td>
            <td>11</td>
        </tr>
        <!-- Y축 행 1 -->
        <tr>
            <td>1</td>
            <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 2 (X=2 에 F) -->
        <tr>
            <td>2</td>
            <td></td><td>F</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 3 (X=2 F, X=3 16) -->
        <tr>
            <td>3</td>
            <td></td><td>F</td><td>16</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 4 (X=2 F, X=3 16, X=7 12) -->
        <tr>
            <td>4</td>
            <td></td><td>F</td><td>16</td><td></td><td></td><td></td><td>12</td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 5 (X=2 F, X=3 16, X=5 16, X=7 12) -->
        <tr>
            <td>5</td>
            <td></td><td>F</td><td>16</td><td></td><td>16</td><td></td><td>12</td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 6 (X=3 16, X=5 16, X=7 12) -->
        <tr>
            <td>6</td>
            <td></td><td></td><td>16</td><td></td><td>16</td><td></td><td>12</td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 7 (X=7 12) -->
        <tr>
            <td>7</td>
            <td></td><td></td><td></td><td></td><td></td><td></td><td>12</td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 8 (X=7 12) -->
        <tr>
            <td>8</td>
            <td></td><td></td><td></td><td></td><td></td><td></td><td>12</td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 9 -->
        <tr>
            <td>9</td>
            <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 10 -->
        <tr>
            <td>10</td>
            <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
        </tr>
        <!-- Y축 행 11 -->
        <tr>
            <td>11</td>
            <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
        </tr>
    </table>
    """
    
    parser = HTMLMatrixTableParser()
    records = parser.parse_matrix_to_records(html)
    
    # 1. 레코드 전체 개수 검증 (X=1..11, Y=1..11 => 121 개)
    assert len(records) == 121
    
    # 2. 공통 메타데이터 정확도 검증
    for r in records:
        assert r["TITLE"] == "AAA"
        assert r["BDIE_LOT"] == "A"
        assert r["BDIE_WF"] == "B"
        assert r["CDIE_LOT"] == "C"
        assert r["CDIE_WF"] == "D"
        
    # 3. 특정 2D 교차점 값 검증
    rec_y2_x2 = [r for r in records if r["X"] == 2 and r["Y"] == 2][0]
    assert rec_y2_x2["VALUE"] == "F"
    
    rec_y3_x3 = [r for r in records if r["X"] == 3 and r["Y"] == 3][0]
    assert rec_y3_x3["VALUE"] == "16"
    
    rec_y4_x7 = [r for r in records if r["X"] == 7 and r["Y"] == 4][0]
    assert rec_y4_x7["VALUE"] == "12"
    
    rec_y5_x5 = [r for r in records if r["X"] == 5 and r["Y"] == 5][0]
    assert rec_y5_x5["VALUE"] == "16"
    
    rec_y8_x7 = [r for r in records if r["X"] == 7 and r["Y"] == 8][0]
    assert rec_y8_x7["VALUE"] == "12"
    
    # 빈 값 검증
    rec_y1_x1 = [r for r in records if r["X"] == 1 and r["Y"] == 1][0]
    assert rec_y1_x1["VALUE"] == ""

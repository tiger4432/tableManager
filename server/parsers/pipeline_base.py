import pandas as pd
import numpy as np
import logging
import math

logger = logging.getLogger("PipelineBase")

class BasePipelineParser:
    """
    AssyManager의 Ingestion 파이프라인을 위한 베이스 클래스입니다.
    이 클래스를 상속받아 개별 파서를 구현하십시오.
    """

    @classmethod
    def match(cls, file_path: str) -> bool:
        """
        주어진 파일을 이 파서가 처리할지 여부를 결정합니다.
        파일명 검사 또는 파일의 첫 줄(헤더)을 읽어 판단할 수 있습니다.
        """
        return False

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Pandas DataFrame을 받아 컬럼 연산, 타입 캐스팅, 전처리 등을 수행합니다.
        자식 클래스에서 이 메서드를 오버라이딩하여 커스텀 로직을 구현합니다.
        """
        return df

    def _read_file_to_dataframe(self, file_path: str) -> pd.DataFrame:
        """
        파일을 읽어 DataFrame으로 반환합니다.
        기본적으로 .csv는 pd.read_csv, .xlsx는 pd.read_excel을 사용합니다.
        필요 시 자식 클래스에서 오버라이딩하여 인코딩이나 구분자를 설정할 수 있습니다.

        🔴 **밑줄로 시작하지만 «공개 확장점»이다. 이름을 바꾸지 말 것.**
        구분자·인코딩·헤더 위치가 다른 소스는 이 메서드를 오버라이드해서 대응하고, 그런
        파서들이 `server/ingestion_workspace/*/scripts/`에 산다 — **그 트리는 gitignore
        대상이라 저장소 검색에 안 잡히고, 운영 박스에는 이 박스에서 보이는 것보다 더 있을 수
        있다.** 개명하면 그 파서들은 오버라이드가 «조용히 무시된 채» 베이스의 read_csv로
        떨어진다 — 예외도 안 나고, 우리가 고칠 수도 없는 곳에서.
        그래서 밑줄은 남기고 계약으로 승격한다: **부르는 것도 오버라이드하는 것도 정상이다.**
        """
        try:
            if file_path.lower().endswith('.csv') or file_path.lower().endswith('.txt'):
                return pd.read_csv(file_path)
            elif file_path.lower().endswith('.xlsx') or file_path.lower().endswith('.xls'):
                return pd.read_excel(file_path)
            else:
                logger.warning(f"Unsupported file extension for pandas default reader: {file_path}")
                # Fallback to CSV if not recognized
                return pd.read_csv(file_path)
        except Exception as e:
            logger.error(f"Failed to read file {file_path} into DataFrame: {e}")
            raise

    def clean_for_postgres(self, df: pd.DataFrame) -> list[dict]:
        """
        PostgreSQL JSONB 컬럼에 에러 없이 저장되도록 DataFrame 내의 비정상 값을 정리합니다.
        - NaN, NaT, Inf 값들을 JSON 표준에 맞는 None(null)으로 치환합니다.
        """
        if df is None or df.empty:
            return []

        # 1. replace numpy NaN and float('nan') with None
        df = df.replace({np.nan: None})
        
        # 2. Iterate and fix remaining Infinity/NaN which replace() might miss depending on types
        records = df.to_dict(orient='records')
        cleaned_records = []
        for record in records:
            clean_record = {}
            for k, v in record.items():
                if pd.isna(v):  # Covers None, NaN, NaT
                    clean_record[k] = None
                elif isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
                    clean_record[k] = None
                else:
                    clean_record[k] = v
            cleaned_records.append(clean_record)
            
        return cleaned_records

    @staticmethod
    def get_basename(file_path: str) -> str:
        """
        추출된 원천 파일의 실제 파일명(유저명 접두사 및 UUID 접미사 제외)을 반환합니다.
        예: user(username)_orig_name_abcdef12.xlsx -> orig_name.xlsx
        """
        import os
        import re
        filename = os.path.basename(file_path)
        # 1. Strip user prefix: user(username)_
        filename = re.sub(r"^user\([^)]+\)_", "", filename)
        # 2. Strip hex suffix before extension: _[0-9a-fA-F]{8}
        name, ext = os.path.splitext(filename)
        name = re.sub(r"_[0-9a-fA-F]{8}$", "", name)
        return name + ext

    def parse(self, file_path: str) -> list[dict]:
        """
        파이프라인의 메인 실행 메서드입니다.
        1. 파일을 DataFrame으로 읽고
        2. 커스텀 연산(process_dataframe)을 수행한 뒤
        3. DB 호환성 클렌징(clean_for_postgres)을 거쳐 리스트 딕셔너리로 반환합니다.
        """
        logger.info(f"Starting pipeline processing for: {file_path}")
        
        # 1. Read
        df = self._read_file_to_dataframe(file_path)
        
        # 2. Process
        processed_df = self.process_dataframe(df)
        
        # 3. Clean & Return
        result = self.clean_for_postgres(processed_df)
        return result


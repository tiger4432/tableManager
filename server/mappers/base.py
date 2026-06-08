import pandas as pd
from typing import List, Dict, Any
from mappers.utils import payloads_to_df

class BaseMapper:
    """
    Master Class (Base Class) for all custom ingestion mappers.
    Provides shared utilities like payloads_to_df for easy DataFrame manipulations.
    """
    
    @staticmethod
    def payloads_to_df(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Converts nested outbox payloads into a flat Pandas DataFrame.
        Delegated to shared utils implementation.
        """
        return payloads_to_df(payloads)

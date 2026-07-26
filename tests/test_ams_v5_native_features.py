import pandas as pd
import pytest
from spotbot.research.ams_v5_native_engine import V5NativeError,assert_boundary,risk_multiplier,drawdown_multiplier
def test_native_boundary_and_risk_contracts():
 assert risk_multiplier(50)==.7 and risk_multiplier(80)==1.2
 assert drawdown_multiplier(.25)==0
 with pytest.raises(V5NativeError):assert_boundary(pd.DataFrame({'bar_open_time':[pd.Timestamp('2025-01-01T00:00:00Z')]}))

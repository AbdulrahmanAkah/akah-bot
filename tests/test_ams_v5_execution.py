# ruff: noqa
import pandas as pd
import pytest
from spotbot.research.ams_v4_active_conviction_swing import AmsV4Error,assert_research_boundary
def test_v5_research_boundary_blocks_2025_open():
 with pytest.raises(AmsV4Error):assert_research_boundary(pd.DataFrame({'bar_open_time':[pd.Timestamp('2025-01-01T00:00:00Z')]}))

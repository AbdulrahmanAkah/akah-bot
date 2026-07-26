import pytest
from spotbot.research.ams_v5_native_engine import trailing_stop
def test_trailing_only_after_contract():
 assert trailing_stop(90,100,2,2.0,None)==(90,None)
 assert trailing_stop(90,100,2,2.25,None)[0]>=93
 assert trailing_stop(95,100,2,3.0,102)[0]>=95

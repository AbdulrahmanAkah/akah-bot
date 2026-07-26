import pandas as pd
from spotbot.research.ams_v5_native_engine import V5OpenPosition,profiles,may_add_on,may_reenter
def test_addon_and_reentry_contracts():
 p=V5OpenPosition('X',100,100,95,95,.007,pd.Timestamp('2024-01-01T00:00Z'),10000,0)
 assert may_add_on(p,106.3,80,False,profiles()[0],0,100000)[0]
 assert not may_add_on(p,100,80,False,profiles()[0],0,100000)[0]
 assert not may_reenter(1,2,False,True,False,False)[0]
 assert may_reenter(1,3,False,True,False,False)[0]

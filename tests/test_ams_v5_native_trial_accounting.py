import pandas as pd
from spotbot.research.ams_v5_native_engine import V5Fill,reconcile_fills
def test_fill_reconciliation():
 a=V5Fill('1','c','p','X',pd.Timestamp('2024-01-01',tz='UTC'),'ENTRY',10,5,50,1,100,49,0,5,'')
 b=V5Fill('2','c','p','X',pd.Timestamp('2024-01-02',tz='UTC'),'STOP_EXIT',9,5,45,1,49,93,5,0,'')
 assert reconcile_fills(100,[a,b])['cash']==93

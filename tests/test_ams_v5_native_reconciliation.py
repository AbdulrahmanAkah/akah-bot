from spotbot.research.ams_v5_native_engine import reconcile_fills
def test_empty_reconciliation():assert reconcile_fills(100,[])['cash']==100

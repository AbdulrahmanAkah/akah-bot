import pandas as pd
from spotbot.research.ams_v5_native_engine import V5Parameters,profiles,simulate_native_fold
def test_empty_native_fold_reconciles_without_positions():
 x=pd.DataFrame({'bar_open_time':[pd.Timestamp('2024-01-01T00:00Z')],'bar_close_time':[pd.Timestamp('2024-01-01T04:00Z')],'symbol':['X'],'open':[10.],'high':[10.],'low':[10.],'close':[10.],'family':['NONE'],'score_no_fib':[0.],'score_soft_fib':[0.],'d1_score':[0.],'eight_hour_score':[0.],'four_hour_score':[0.],'fib':[0.],'atr':[1.],'tradable_from':[pd.Timestamp('2020-01-01T00:00Z')],'tradable_until':[pd.Timestamp('2025-01-01T00:00Z')]})
 r=simulate_native_fold(four_hour_panel=x,configuration=V5Parameters('A','HYBRID_ALL_THREE','STRUCTURE_BALANCED','NO_FIBONACCI',50,.002),portfolio_profile=profiles()[0],selected_threshold=50,transaction_cost=.002)
 assert r.final_cash==100000 and r.open_positions_after_fold==0

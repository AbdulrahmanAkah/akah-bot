from spotbot.research.ams_v5_native_engine import choose_threshold
def test_threshold_train_objective_and_tie():
 x={50:{'profit_factor':1.2,'maximum_drawdown':.1,'expectancy':1,'calmar':1,'activity_alignment':1,'stress_resilience':1},55:{'profit_factor':1.2,'maximum_drawdown':.1,'expectancy':1,'calmar':1,'activity_alignment':1,'stress_resilience':1}}
 assert choose_threshold(x)['selected']==55

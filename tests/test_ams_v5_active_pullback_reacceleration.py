# ruff: noqa
from spotbot.research.ams_v5_active_pullback_reacceleration import build_configuration_grid, portfolio_profiles
def test_grid_and_profiles_are_registered():
 assert len(build_configuration_grid())==12
 assert len({x['parameter_hash_sha256'] for x in build_configuration_grid()})==12
 assert [x.profile_id for x in portfolio_profiles()]==['AMS-V5-PORTFOLIO-P01','AMS-V5-PORTFOLIO-P02']

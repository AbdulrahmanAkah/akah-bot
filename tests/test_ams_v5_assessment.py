# ruff: noqa
from scripts.research.assess_ams_v5 import activity
def test_v5_activity_boundaries():
 assert activity(89)=='VERY_SPARSE'
 assert activity(120)=='MODERATE_ACTIVITY'
 assert activity(160)=='TARGET_ACTIVITY'

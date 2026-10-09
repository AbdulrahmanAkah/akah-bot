import random
from datetime import datetime,timedelta,timezone

import pytest

from spotbot.research.multi_school_fidelity.integration_v13.fast_prefix import FastCompletedPrefix
from spotbot.research.multi_school_fidelity.integration_v9.sources import CompletedPrefix
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar,ContractError


@pytest.mark.parametrize("degree,step",[("1H",1),("4H",4),("1D",24)])
def test_exact_native_parity_for_random_gap_and_tied_extrema(degree,step):
    a=CompletedPrefix("X-USDT","A"*64)
    b=FastCompletedPrefix("X-USDT","A"*64)
    t=datetime(2023,1,1,tzinfo=timezone.utc)
    rng=random.Random(784)
    for i in range(100):
        close=100+round(rng.uniform(-8,8),1)
        # Repeated rounded extremes stress native uniqueness/tie behavior.
        row=CompletedBar(t,t+timedelta(hours=step),degree,100, max(101,close+2),min(99,close-2),close)
        assert a.on_close(row,10,row.end)==b.on_close(row,10,row.end)
        assert a.graph.nodes==b.graph.nodes and a.points==b.points
        if i>=9:
            assert a.atr(degree,"unused",row.end)==b.atr(degree,"unused",row.end)
        t=row.end
    with pytest.raises(ContractError):
        b.on_close(row,10,row.end)

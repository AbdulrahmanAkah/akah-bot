import pandas as pd
import numpy as np
import pytest
import gc
from spotbot.research.multi_school_fidelity.gate3_market_v3 import bounded_sha
from v15_input_memorymap import cache_frame


@pytest.mark.parametrize('unit',['us','ns'])
def test_exact_input_units_values_hash_readonly_and_tamper(tmp_path,unit):
    times=pd.date_range('2022-01-01',periods=5,freq='h',tz='UTC').as_unit(unit)
    frame=pd.DataFrame({'timestamp':times,'open':[1.1]*5,'high':[2.3]*5,'low':[.5]*5,
                        'close':[1.2]*5,'volume':[123.4567]*5})
    expected=bounded_sha(frame)
    actual=cache_frame(frame,tmp_path,expected)
    pd.testing.assert_frame_equal(frame,actual,check_exact=True)
    assert not actual['open'].to_numpy().flags.writeable
    assert not actual['timestamp'].array.asi8.flags.writeable
    assert isinstance(actual['timestamp'].array._ndarray.base,np.ndarray)
    assert bounded_sha(actual)==expected
    del actual
    gc.collect()
    with (tmp_path/'open.npy').open('wb') as stream:np.save(stream,np.array([8.8]*5),allow_pickle=False)
    with pytest.raises(RuntimeError,match='BOUNDED_ROW_PARITY_FAILED'):
        cache_frame(frame,tmp_path,expected)

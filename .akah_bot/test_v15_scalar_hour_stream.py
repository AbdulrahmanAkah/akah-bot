"""Synthetic pre-2024 clock fixtures and retained-heap forensic, no replay."""
import gc
import json
import tracemalloc
from pathlib import Path
import pandas as pd
import pytest
from v15_scalar_hour_stream import ORIGINAL, hours


def frame(unit='ns', rows=96):
    times=pd.date_range('2022-01-01', periods=rows, freq='h', tz='UTC').as_unit(unit)
    return pd.DataFrame({'timestamp':times,'open':[1.01]*rows,'high':[1.04]*rows,
                        'low':[.91]*rows,'close':[1.02]*rows,'volume':[123.789]*rows})


@pytest.mark.parametrize('unit',['us','ns'])
def test_every_scalar_bar_volume_order_and_exclusion_exact(unit):
    f=frame(unit)
    for start,end in [('2022-01-01','2022-01-05'),('2022-01-02','2022-01-03')]:
        assert list(hours(f,start,end))==list(ORIGINAL(f,start,end))


def test_irregular_missing_hours_and_fractional_time_conversion_exact():
    f=frame().iloc[[0,1,3,8,30,41,62,95]].copy()
    assert list(hours(f,'2022-01-01','2022-01-05'))==list(ORIGINAL(f,'2022-01-01','2022-01-05'))


def test_unknown_column_representation_uses_native_path():
    f=frame();f['extra']=3
    assert list(hours(f,'2022-01-01','2022-01-05'))==list(ORIGINAL(f,'2022-01-01','2022-01-05'))


def test_first_row_does_not_pin_eight_timestamp_batches():
    f=frame(rows=12000)
    def retained(factory):
        gc.collect();tracemalloc.start()
        streams=[factory(f,'2022-01-01','2023-12-01') for _ in range(8)]
        values=[next(s) for s in streams]
        memory=tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        for s in streams:s.close()
        return memory,values
    native, a=retained(ORIGINAL)
    scalar, b=retained(hours)
    assert a==b
    # Resource regression only, not an economic acceptance threshold.
    assert scalar<native/5
    receipt={'native_retained_bytes':native,
          'scalar_retained_bytes':scalar,'streams':8,'rows_per_fixture':12000,
          'first_output_exact':True,'market_rows_read':0,'economic_replay_executed':False}
    (Path(__file__).resolve().parent/'v15_timestamp_batch_forensic.json').write_text(
        json.dumps(receipt,indent=2)+'\n')
    print('TIMESTAMP_BATCH_FORENSIC='+json.dumps(receipt),flush=True)

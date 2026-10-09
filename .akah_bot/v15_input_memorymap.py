"""Canonical predicate validation remains; retain read-only arrays, not raw heaps."""
import gc
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa

from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import raw_frame as ORIGINAL
from spotbot.research.multi_school_fidelity.gate3_market_v3 import bounded_sha

ROOT=Path(__file__).resolve().parents[1]
COLUMNS=('timestamp','open','high','low','close','volume')
INSTALLED=False


def cache_frame(frame,directory,expected):
    directory=Path(directory)
    metadata=directory/'metadata.json'
    if not metadata.exists():
        directory.mkdir(parents=True,exist_ok=True)
        unit=frame.timestamp.dtype.unit
        for name in COLUMNS:
            value=frame[name].array.asi8 if name=='timestamp' else frame[name].to_numpy()
            path=directory/(name+'.npy')
            if path.exists():raise RuntimeError('INCOMPLETE_CACHE_REQUIRES_EXPLICIT_RECOVERY_NOT_OVERWRITE')
            with path.open('xb') as stream:np.save(stream,value,allow_pickle=False)
        metadata.write_text(json.dumps({'bounded_sha256':expected,'rows':len(frame),'timestamp_unit':unit,
                                        'columns':list(COLUMNS)},indent=2)+'\n')
    meta=json.loads(metadata.read_text())
    if meta['bounded_sha256']!=expected or meta['rows']!=len(frame) or meta['columns']!=list(COLUMNS):
        raise RuntimeError('MEMORYMAP_INPUT_CACHE_BINDING_DRIFT')
    # ndarray VIEW of the read-only mapping, not an eager heap copy. Preserve
    # pandas' original ndarray class as well as scalar/dtype semantics.
    values={name:np.asarray(np.load(directory/(name+'.npy'),mmap_mode='r',allow_pickle=False)) for name in COLUMNS}
    # Already-authoritative UTC integer instants need no timezone conversion.
    # pd.to_datetime(..., utc=True) copies the whole timestamp vector into the
    # private heap for EACH simultaneous input stream. Preserve an exact,
    # read-only file-backed DatetimeArray using this installed pandas API.
    native_times=values['timestamp'].view('datetime64['+meta['timestamp_unit']+']')
    values['timestamp']=pd.arrays.DatetimeArray._simple_new(native_times,
        dtype=pd.DatetimeTZDtype(unit=meta['timestamp_unit'],tz='UTC'))
    result=pd.DataFrame(values,columns=COLUMNS,copy=False)
    if result['timestamp'].array.asi8.flags.writeable:
        raise RuntimeError('READONLY_TIMESTAMP_MAPPING_REQUIRED')
    if bounded_sha(result)!=expected:raise RuntimeError('MEMORYMAP_BOUNDED_ROW_PARITY_FAILED')
    return result


def raw_frame(repo,pair,*args,**kwargs):
    # Re-read and validate canonical pre-2024 raw rows for each invocation;
    # source drift cannot be concealed by a metadata-only cache shortcut.
    frame=ORIGINAL(repo,pair,*args,**kwargs)
    actual=bounded_sha(frame)
    result=cache_frame(frame,ROOT/'.akah_bot/v15_bounded_input_cache'/actual/pair,actual)
    del frame
    gc.collect(0)
    pa.default_memory_pool().release_unused()
    return result


def install():
    global INSTALLED
    if INSTALLED:return
    pa.set_cpu_count(1);pa.set_io_thread_count(1)
    from scripts.research.integration_v15 import runner
    runner.raw_frame=raw_frame
    INSTALLED=True

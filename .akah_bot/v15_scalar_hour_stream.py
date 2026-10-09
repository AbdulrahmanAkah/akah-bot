"""Avoid one retained pandas 10,000-Timestamp batch per live market stream.

Same authoritative scalar conversion, ordering and bounds. No buffering future
bars, dtype rounding, altered OHLCV or bypass of bounded input SHA checks.
"""
from datetime import timedelta
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import utc
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar
from scripts.research.integration_v15 import runner

ORIGINAL = runner.hours
INSTALLED = False
COLUMNS = ('timestamp', 'open', 'high', 'low', 'close', 'volume')


def hours(frame, start, end):
    # Unsupported representations retain the native path, not a guessed one.
    if tuple(frame.columns) != COLUMNS:
        yield from ORIGINAL(frame, start, end)
        return
    times = frame['timestamp'].array
    values = [frame[c].to_numpy(copy=False) for c in COLUMNS[1:]]
    lower = utc(start).to_pydatetime()
    upper = utc(end).to_pydatetime()
    for i in range(len(frame)):
        close = utc(times[i]).to_pydatetime()
        begin = close - timedelta(hours=1)
        if begin < lower or close >= upper:
            continue
        yield CompletedBar(begin, close, '1H', *(float(v[i]) for v in values[:4])), float(values[4][i])


def install():
    global INSTALLED
    if not INSTALLED:
        runner.hours = hours
        INSTALLED = True

from datetime import datetime,timedelta,timezone
import copy
import v15_disk_history as disk
import v15_checkpoints as checkpoints
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar


def test_file_vectors_growth_precision_mutation_checkpoint_repeatability(tmp_path):
    start=datetime(2021,9,1,tzinfo=timezone.utc)
    values=[CompletedBar(start+timedelta(hours=i,microseconds=123),start+timedelta(hours=i+1,microseconds=123),
             '1H',1.123456789012345,3.,.123456789012345,2.) for i in range(1050)]
    bars=disk.DiskPackedBars('1H')
    for bar in values:bars.append(bar)
    assert list(bars)==values and bars[::-2]==values[::-2]
    other=copy.deepcopy(bars);assert list(other)==values
    bars[17]=values[18];values[17]=values[18]
    del bars[-1];del values[-1]
    bars.insert(10,values[15]);values.insert(10,values[15])
    assert list(bars)==values
    authority={'purpose':'SYNTHETIC_EXACT_DISK_HISTORY'}
    path=checkpoints.write_checkpoint(tmp_path,{'bars':bars},authority)
    bars.append(values[-1])
    restored=checkpoints.read_checkpoint(path,authority)['bars']
    assert list(restored)==values
    restored.append(values[-1])
    again=checkpoints.read_checkpoint(path,authority)['bars']
    assert list(again)==values


def test_whole_source_disk_history_resume(tmp_path):
    disk.install()
    from test_v15_checkpoints import provider,advance,signature
    p=provider();advance(p,0,36)
    assert isinstance(p.feeds['BTC-USDT'].prefix.bars['1H'].times,disk.MappedVector)
    authority={'purpose':'SYNTHETIC_ALL_SOURCE_DISK_HISTORY'}
    expected=signature(p)
    path=checkpoints.write_checkpoint(tmp_path,{'source':p},authority)
    restored=checkpoints.read_checkpoint(path,authority)['source']
    advance(p,36,60);advance(restored,36,60)
    assert signature(p)==signature(restored)
    assert signature(checkpoints.read_checkpoint(path,authority)['source'])==expected

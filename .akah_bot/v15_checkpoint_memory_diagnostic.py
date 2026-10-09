"""Read one trusted local checkpoint, summarize retained state, no market rows."""
import json
from collections import Counter
from pathlib import Path
import sys
from v15_resource_guard import ROOT, resources
from v15_checkpoints import read_checkpoint, sha
import v15_disk_history as history
import cache_budget_v15

history.install(); cache_budget_v15.install()
pointer=json.loads((ROOT/'.akah_bot/v15_recoverable_session/FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json').read_text())
receipt=Path(pointer['receipt'])
if sha(receipt)!=pointer['sha256']:raise RuntimeError('CHECKPOINT_POINTER_DRIFT')
contract=json.loads(receipt.read_text())
saved=read_checkpoint(receipt,contract['authority'])
source=saved['driver'].source
report={'cursor':str(saved['scheduler']['cursor']),'resources':resources(),'source_fields':{},'retained':{}}
for key,value in vars(source).items():
    if isinstance(value,(dict,list,set,tuple)):
        report['source_fields'][key]={'length':len(value),'shallow_bytes':sys.getsizeof(value)}
graphs={id(f.prefix.graph):f.prefix.graph for f in source.feeds.values()}
for i,g in enumerate(graphs.values()):
    report['retained']['graph_'+str(i)]={
        k:{'length':len(v),'shallow_bytes':sys.getsizeof(v)} for k,v in vars(g).items()
        if isinstance(v,(dict,list,set,tuple))}
    report['retained']['archive_mutable_origins']=dict(Counter(n.origin for n in g.nodes.mutable.values()))
counts=Counter();bytes_=Counter()
for pair,feed in source.feeds.items():
    counts['prefix.points']+=len(feed.prefix.points)
    for school in ('elliott','harmonic','classical','wyckoff','ict'):
        obj=getattr(feed,school,None)
        if obj is None:continue
        for k,v in vars(obj).items():
            if isinstance(v,(dict,list,set,tuple)):
                counts[school+'.'+k]+=len(v);bytes_[school+'.'+k]+=sys.getsizeof(v)
        search=getattr(obj,'_search',None)
        if search is not None:
            for k,v in vars(search).items():
                if isinstance(v,(dict,list,set,tuple)):
                    counts[school+'.search.'+k]+=len(v);bytes_[school+'.search.'+k]+=sys.getsizeof(v)
report['counts']=dict(counts);report['shallow_bytes']=dict(bytes_)
print(json.dumps(report,indent=2),flush=True)

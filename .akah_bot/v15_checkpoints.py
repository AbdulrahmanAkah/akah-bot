"""Atomic, SHA-bound exact Python-state snapshots and immutable source archives.

Only this process's generated checkpoints may be loaded. No external pickle,
look-ahead, fabricated completed bars or economic state recomputation.
"""
from collections import OrderedDict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import pickle
import sqlite3
import tempfile
import shutil

import v15_bounded_storage as storage
import v15_scaling_acceleration as scaling
import v15_disk_history as disk


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest().upper()


def restore_archive(path,capacity):
    # Stateful fields are restored by pickle only after all cyclic references
    # have been allocated. No archive is queried before state restoration.
    value=storage.EvidenceArchive.__new__(storage.EvidenceArchive)
    # Resume from a NEW mutable working copy, never mutate the SHA-bound
    # immutable checkpoint archive. The same checkpoint remains reloadable.
    directory=storage.ROOT/'.akah_bot/v15_runtime_spill'
    directory.mkdir(parents=True,exist_ok=True)
    handle=tempfile.NamedTemporaryFile(prefix='resumed-source-',suffix='.sqlite',dir=directory,delete=False)
    working=Path(handle.name);handle.close();shutil.copyfile(path,working)
    value.path=working;value.capacity=capacity
    value.connection=sqlite3.connect(value.path)
    value.connection.execute('PRAGMA cache_size=-2048')
    value.cache=OrderedDict();value.mutable={}
    return value


def restore_set(cls,values):
    value=cls(None)
    set.update(value,values)
    return value


class SnapshotPickler(pickle.Pickler):
    def __init__(self,stream,directory):
        super().__init__(stream,protocol=5)
        self.directory=Path(directory);self.archives={}

    def reducer_override(self,value):
        import v15_disk_seen as seen
        if isinstance(value,seen.DiskSeen):
            source=str(value.store.path.resolve())
            if source not in self.archives:
                destination=self.directory/f'seen_{len(self.archives)}.sqlite'
                value.store.commit()
                with sqlite3.connect(destination) as saved:value.store.connection.backup(saved)
                self.archives[source]={'path':str(destination),'sha256':sha(destination)}
            return (seen.restore_seen,(self.archives[source]['path'],value.ns,value.count),
                    {'fallback':value.fallback})
        import v15_diagnostic_journal as journal
        if isinstance(value,journal.DiagnosticJournal):
            source=str(value.store.path.resolve())
            if source not in self.archives:
                destination=self.directory/f'diagnostics_{len(self.archives)}.sqlite'
                value.store.commit()
                with sqlite3.connect(destination) as saved:value.store.connection.backup(saved)
                self.archives[source]={'path':str(destination),'sha256':sha(destination)}
            # Mutable diagnostics stay by reference and participate in the
            # common pickler memo. Bind store separately in BUILD for cycles.
            return (journal.restore_journal,(self.archives[source]['path'],value.j,value.count,{}),
                    {'mutable':value.mutable})
        if isinstance(value,disk.MappedVector):
            source=str(value.path.resolve())
            if source not in self.archives:
                destination=self.directory/f'vector_{len(self.archives)}.bin'
                value.mapping.flush();shutil.copyfile(value.path,destination)
                self.archives[source]={'path':str(destination),'sha256':sha(destination)}
            return (disk.restore_vector,(self.archives[source]['path'],value.code,value.length,value.capacity))
        if isinstance(value,storage.EvidenceArchive):
            source=str(value.path.resolve())
            if source not in self.archives:
                destination=self.directory/f'archive_{len(self.archives)}.sqlite'
                value.connection.commit()
                with sqlite3.connect(destination) as saved:
                    value.connection.backup(saved)
                self.archives[source]={'path':str(destination),'sha256':sha(destination)}
            state={k:v for k,v in value.__dict__.items() if k not in {'connection','cache','path'}}
            state['cache']=OrderedDict() # Pure retrieval cache, not semantic state.
            return (restore_archive,(self.archives[source]['path'],value.capacity),state)
        if isinstance(value,scaling.PointJournal):
            return (scaling.PointJournal,(),value.__dict__,None,iter(value.items()))
        if isinstance(value,scaling.base.EpochSet):
            return (restore_set,(type(value),tuple(value)),value.__dict__)
        if isinstance(value,scaling.base.EpochDict):
            return (type(value),(None,),value.__dict__,None,iter(value.items()))
        return NotImplemented


class Certificates:
    def __init__(self,certificates):self.certificates=tuple(certificates)
    def __call__(self,now,frozen,grammar):
        return (next(c for c in self.certificates if c.grammar==grammar),)


def write_checkpoint(directory,state,authority):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    # Retain every preceding checkpoint. Never overwrite a prior authority.
    dest=Path(tempfile.mkdtemp(prefix='checkpoint-',dir=directory))
    temporary=dest/'state.pending'
    with temporary.open('xb') as stream:
        encoder=SnapshotPickler(stream,dest)
        encoder.dump(state);stream.flush();os.fsync(stream.fileno())
    path=dest/'state.pickle';os.replace(temporary,path)
    receipt={'authority':authority,'state_path':str(path),'state_sha256':sha(path),
        'archives':list(encoder.archives.values()),'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'EXACT_RUNTIME_CHECKPOINT_NOT_COMPLETED_ECONOMIC_RESULT',
        'format':'TRUSTED_LOCAL_PICKLE_PROTOCOL_5','outside_pickle_inputs_permitted':False}
    (dest/'receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n')
    return dest/'receipt.json'


def read_checkpoint(receipt_path,expected_authority):
    receipt_path=Path(receipt_path).resolve()
    receipt=json.loads(receipt_path.read_text())
    if receipt['authority']!=expected_authority:
        raise RuntimeError('CHECKPOINT_AUTHORITY_DRIFT')
    root=receipt_path.parent
    for binding in [{'path':receipt['state_path'],'sha256':receipt['state_sha256']},*receipt['archives']]:
        path=Path(binding['path']).resolve()
        if not path.is_relative_to(root) or sha(path)!=binding['sha256']:
            raise RuntimeError('CHECKPOINT_CONTENT_OR_PATH_DRIFT')
    import v15_diagnostic_journal as journal
    import v15_disk_seen as seen
    # Repeated checkpoint loads must never reuse a previously mutated working
    # log. Sharing is only within THIS unpickle operation, not across resumes.
    for binding in receipt['archives']:
        key=str(Path(binding['path']).resolve())
        journal.STORES.pop(key,None);seen.STORES.pop(key,None)
    with Path(receipt['state_path']).open('rb') as stream:return pickle.load(stream)

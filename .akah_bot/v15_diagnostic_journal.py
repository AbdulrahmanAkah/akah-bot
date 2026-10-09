"""Lossless disk-backed append-only runtime diagnostics, NOT source pruning.

Native Harmonic diagnostics contain many rejected quartet/family records. They
are never read to choose an action, but retaining all of them as Python tuples
grows the heap. This journal retains every record and its insertion order.
Only recursively immutable built-in records may leave the heap; unknown or
mutable records stay by reference. No economic/history/proof record is dropped.
"""
from collections.abc import MutableSequence, Sequence
from datetime import datetime, timedelta
import copy
import hashlib
from pathlib import Path
import pickle
import sqlite3
import tempfile

ROOT=Path(__file__).resolve().parents[1]
STORES={}
CURRENT=None
INSTALLED=False
ORIGINAL_INIT=None


def immutable(value):
    if type(value) in (str,int,float,bool,type(None),datetime,timedelta):return True
    return type(value) is tuple and all(immutable(v) for v in value)


class Store:
    def __init__(self,path=None):
        directory=ROOT/'.akah_bot/v15_runtime_spill';directory.mkdir(parents=True,exist_ok=True)
        if path is None:
            f=tempfile.NamedTemporaryFile(prefix='diagnostics-',suffix='.sqlite',dir=directory,delete=False)
            path=f.name;f.close()
        self.path=Path(path)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute('PRAGMA cache_size=-512')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE IF NOT EXISTS log(j INTEGER,n INTEGER,p BLOB,s TEXT,PRIMARY KEY(j,n))')
        self.serial=self.connection.execute('SELECT COALESCE(MAX(j),0) FROM log').fetchone()[0]
        self.writes=0
        STORES[str(self.path.resolve())]=self
    def allocate(self):self.serial+=1;return self.serial
    def commit(self):self.connection.commit()
    def __del__(self):
        try:self.connection.commit();self.connection.close()
        except Exception:pass


def store():
    global CURRENT
    if CURRENT is None:CURRENT=Store()
    return CURRENT


class DiagnosticJournal(MutableSequence):
    def __init__(self,values=()):
        self.store=store();self.j=self.store.allocate();self.count=0;self.mutable={}
        self.extend(values)
    def __len__(self):return self.count
    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(self.count))]
        if index<0:index+=self.count
        if index<0 or index>=self.count:raise IndexError('list index out of range')
        if index in self.mutable:return self.mutable[index]
        row=self.store.connection.execute('SELECT p,s FROM log WHERE j=? AND n=?',(self.j,index)).fetchone()
        if row is None:raise RuntimeError('DIAGNOSTIC_RECORD_MISSING')
        payload,binding=row
        if payload is None:raise RuntimeError('MUTABLE_DIAGNOSTIC_NOT_IN_LIVE_PROCESS')
        if hashlib.sha256(payload).hexdigest()!=binding:raise RuntimeError('DIAGNOSTIC_CONTENT_DRIFT')
        return pickle.loads(payload) # Self-created, checksum-bound only.
    def append(self,value):
        if immutable(value):
            p=pickle.dumps(value,protocol=5);s=hashlib.sha256(p).hexdigest()
        else:p=s=None;self.mutable[self.count]=value
        self.store.connection.execute('INSERT INTO log VALUES(?,?,?,?)',(self.j,self.count,p,s))
        self.count+=1;self.store.writes+=1
        if self.store.writes%1024==0:self.store.commit()
    def __eq__(self,other):
        return isinstance(other,Sequence) and len(self)==len(other) and all(a==b for a,b in zip(self,other))
    def _rebuild(self,values):
        self.store.connection.execute('DELETE FROM log WHERE j=?',(self.j,))
        self.count=0;self.mutable={};self.extend(values)
    def __setitem__(self,index,value):
        values=list(self);values[index]=value;self._rebuild(values)
    def __delitem__(self,index):
        values=list(self);del values[index];self._rebuild(values)
    def insert(self,index,value):
        values=list(self);values.insert(index,value);self._rebuild(values)
    def copy(self):return list(self)
    def __deepcopy__(self,memo):
        result=type(self)();memo[id(self)]=result
        for record in self:result.append(copy.deepcopy(record,memo))
        return result


def restore_journal(path,j,count,mutable):
    key=str(Path(path).resolve())
    if key not in STORES:
        # A checkpoint is immutable. Resume into a new working database.
        import shutil
        restored=Store();restored.connection.close();shutil.copyfile(path,restored.path)
        restored.connection=sqlite3.connect(restored.path)
        restored.connection.execute('PRAGMA cache_size=-512')
        restored.serial=restored.connection.execute('SELECT COALESCE(MAX(j),0) FROM log').fetchone()[0]
        STORES[key]=restored
    result=DiagnosticJournal.__new__(DiagnosticJournal)
    result.store=STORES[key];result.j=j;result.count=count;result.mutable=mutable
    result.store.serial=max(result.store.serial,j)
    return result


def source_init(self,*args,**kwargs):
    ORIGINAL_INIT(self,*args,**kwargs)
    self.diagnostics=DiagnosticJournal(self.diagnostics)


def install():
    global INSTALLED,ORIGINAL_INIT
    if INSTALLED:return
    from spotbot.research.multi_school_fidelity.integration_v13.harmonic_source import HarmonicSource
    ORIGINAL_INIT=HarmonicSource.__init__;HarmonicSource.__init__=source_init
    INSTALLED=True

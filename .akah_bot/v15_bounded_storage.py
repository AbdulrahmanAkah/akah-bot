"""Supplemental storage representation, NOT an economic policy change.

Compact bar history preserves all elements, indices and slices. Source evidence
uses an insertion-ordered SQLite archive with bounded immutable-object cache.
Mutable values remain by reference; nothing is expired or discarded.
"""
from array import array
from collections import OrderedDict
from collections.abc import MutableMapping, MutableSequence, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import pickle
from pathlib import Path
import sqlite3
import tempfile
import copy

import v15_indexed_acceleration as indexed
import v15_scaling_acceleration as scaling
from spotbot.research.multi_school_fidelity.integration_v9.sources import CompletedPrefix, SourceGraph
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar, ContractError

ROOT=Path(__file__).resolve().parents[1]
GRAPH_INIT=SourceGraph.__init__
PREFIX_INIT=CompletedPrefix.__init__
INSTALLED=False
EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)


def immutable(value):
    if type(value) in {str,int,float,bool,type(None),datetime,timedelta}:return True
    if type(value) is tuple:return all(immutable(v) for v in value)
    return (is_dataclass(value) and value.__dataclass_params__.frozen and
            all(immutable(getattr(value,f.name)) for f in fields(value)))


class PackedBars(MutableSequence):
    def __init__(self,degree):
        self.degree=degree
        self.times=array('q')
        self.prices=array('d')
        self.fallback={}
        self.cache=OrderedDict()

    def __len__(self):return len(self.times)//2

    def append(self,bar):
        i=len(self)
        # Non-native/subclass values preserve original object semantics exactly.
        if (type(bar) is not CompletedBar or bar.timeframe!=self.degree or
            type(bar.start) is not datetime or bar.start.tzinfo is not timezone.utc or
            type(bar.end) is not datetime or bar.end.tzinfo is not timezone.utc or
            any(type(v) is not float for v in (bar.open,bar.high,bar.low,bar.close))):
            self.fallback[i]=bar
            self.times.extend((0,0));self.prices.extend((0.,0.,0.,0.))
        else:
            for t in (bar.start,bar.end):
                delta=t-EPOCH
                self.times.append((delta.days*86400+delta.seconds)*1000000+delta.microseconds)
            self.prices.extend((bar.open,bar.high,bar.low,bar.close))
        self.cache[i]=bar
        if len(self.cache)>32:self.cache.popitem(last=False)

    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self)))]
        if index<0:index+=len(self)
        if index<0 or index>=len(self):raise IndexError('list index out of range')
        if index in self.fallback:return self.fallback[index]
        if index in self.cache:return self.cache[index]
        value=CompletedBar(EPOCH+timedelta(microseconds=self.times[index*2]),
            EPOCH+timedelta(microseconds=self.times[index*2+1]),self.degree,
            *self.prices[index*4:index*4+4])
        self.cache[index]=value
        if len(self.cache)>32:self.cache.popitem(last=False)
        return value

    def __eq__(self,other):
        return isinstance(other,Sequence) and len(self)==len(other) and all(a==b for a,b in zip(self,other))

    def _rebuild(self,values):
        self.times=array('q');self.prices=array('d');self.fallback={};self.cache.clear()
        for value in values:self.append(value)

    def __setitem__(self,index,value):
        # Mutation is supported, NOT silently discarded. Subsequent source
        # authority checks retain the frozen producer's rejection semantics.
        values=list(self);values[index]=value;self._rebuild(values)

    def __delitem__(self,index):
        values=list(self);del values[index];self._rebuild(values)

    def insert(self,index,value):
        values=list(self);values.insert(index,value);self._rebuild(values)

    def copy(self):return list(self)


class EvidenceArchive(MutableMapping):
    def __init__(self,owner,*,capacity=8192,path=None):
        self.owner=owner;self.capacity=capacity
        directory=ROOT/'.akah_bot/v15_runtime_spill';directory.mkdir(parents=True,exist_ok=True)
        if path is None:
            handle=tempfile.NamedTemporaryFile(prefix='source-',suffix='.sqlite',dir=directory,delete=False)
            path=handle.name;handle.close()
        self.path=Path(path)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute('PRAGMA cache_size=-2048')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE IF NOT EXISTS nodes (seq INTEGER PRIMARY KEY, eid TEXT UNIQUE NOT NULL, payload BLOB, sha TEXT)')
        self.connection.execute('CREATE INDEX IF NOT EXISTS eid_index ON nodes(eid)')
        self.cache=OrderedDict();self.mutable={};self.writes=0
        self.bloom=bytearray(2**20)
        self.count=0
        for (eid,) in self.connection.execute('SELECT eid FROM nodes ORDER BY seq'):
            self._mark(eid);self.count+=1

    def _bits(self,key):
        h=hashlib.blake2b(str(key).encode(),digest_size=16).digest()
        mask=len(self.bloom)*8-1
        return (int.from_bytes(h[:8],'little')&mask,int.from_bytes(h[8:],'little')&mask)

    def _mark(self,key):
        for b in self._bits(key):self.bloom[b//8]|=1<<(b%8)

    def __contains__(self,key):
        if key in self.cache or key in self.mutable:return True
        if any(not self.bloom[b//8]&(1<<(b%8)) for b in self._bits(key)):return False
        return self.connection.execute('SELECT 1 FROM nodes WHERE eid=?',(key,)).fetchone() is not None

    def __len__(self):return self.count

    def __iter__(self):
        return (eid for (eid,) in self.connection.execute('SELECT eid FROM nodes ORDER BY seq'))

    def _cache(self,key,value):
        self.cache[key]=value;self.cache.move_to_end(key)
        if len(self.cache)>self.capacity:self.cache.popitem(last=False)

    def __getitem__(self,key):
        if key in self.mutable:return self.mutable[key]
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        row=self.connection.execute('SELECT payload,sha FROM nodes WHERE eid=?',(key,)).fetchone()
        if row is None:raise KeyError(key)
        payload,sha=row
        if payload is None:raise ContractError('MUTABLE_ARCHIVE_VALUE_NOT_IN_LIVE_PROCESS')
        if hashlib.sha256(payload).hexdigest()!=sha:raise ContractError('SOURCE_ARCHIVE_CONTENT_DRIFT')
        # Only self-generated, SHA-checked local payloads; never external pickle.
        value=pickle.loads(payload)
        self._cache(key,value);return value

    def invalidate(self):
        self.owner._scaling_destructive_revision+=1
        self.owner._exact_epoch+=1
        self.owner._exact_live.clear();self.owner._exact_native.clear()

    def __setitem__(self,key,value):
        exists=key in self
        if exists:self.invalidate()
        if immutable(value):
            payload=pickle.dumps(value,protocol=5);sha=hashlib.sha256(payload).hexdigest()
            self.mutable.pop(key,None)
        else:
            payload=sha=None;self.mutable[key]=value
        if exists:self.connection.execute('UPDATE nodes SET payload=?,sha=? WHERE eid=?',(payload,sha,key))
        else:
            self.connection.execute('INSERT INTO nodes(eid,payload,sha) VALUES (?,?,?)',(key,payload,sha))
            self.count+=1;self._mark(key)
        self._cache(key,value)
        self.writes+=1
        if self.writes%1024==0:self.connection.commit()

    def __delitem__(self,key):
        if key not in self:raise KeyError(key)
        self.invalidate();self.connection.execute('DELETE FROM nodes WHERE eid=?',(key,))
        self.mutable.pop(key,None);self.cache.pop(key,None);self.count-=1

    def clear(self):
        self.invalidate();self.connection.execute('DELETE FROM nodes')
        self.mutable.clear();self.cache.clear();self.bloom=bytearray(len(self.bloom));self.count=0

    def popitem(self):
        row=self.connection.execute('SELECT eid FROM nodes ORDER BY seq DESC LIMIT 1').fetchone()
        if row is None:raise KeyError('popitem(): dictionary is empty')
        key=row[0];value=self[key];del self[key];return key,value

    def copy(self):return dict(self.items())

    def __deepcopy__(self,memo):
        # Native admission previews copy the source graph. SQLite handles are
        # not Python-copyable; create an independent exact database snapshot,
        # and preserve cyclic graph/prefix ownership via deepcopy's memo.
        result=type(self).__new__(type(self));memo[id(self)]=result
        directory=ROOT/'.akah_bot/v15_runtime_spill'
        directory.mkdir(parents=True,exist_ok=True)
        handle=tempfile.NamedTemporaryFile(prefix='preview-source-',suffix='.sqlite',dir=directory,delete=False)
        result.path=Path(handle.name);handle.close()
        self.connection.commit()
        result.connection=sqlite3.connect(result.path)
        self.connection.backup(result.connection)
        result.connection.execute('PRAGMA cache_size=-2048')
        for key,value in self.__dict__.items():
            if key not in {'path','connection'}:setattr(result,key,copy.deepcopy(value,memo))
        return result

    def __ior__(self,other):
        self.update(other);return self

    def close(self):
        if self.connection is not None:
            self.connection.commit();self.connection.close();self.connection=None

    def __del__(self):
        try:self.close()
        except Exception:pass


def graph_init(self):
    GRAPH_INIT(self)
    self.nodes=EvidenceArchive(self)
    self._exact_nodes_object=self.nodes


def prefix_init(self,*args,**kwargs):
    PREFIX_INIT(self,*args,**kwargs)
    self.bars={d:PackedBars(d) for d in self.bars}


def install():
    global INSTALLED,GRAPH_INIT,PREFIX_INIT
    if INSTALLED:return
    indexed.install()
    # Capture the actually installed scaling methods, not stale import order.
    GRAPH_INIT=SourceGraph.__init__;PREFIX_INIT=CompletedPrefix.__init__
    SourceGraph.__init__=graph_init;CompletedPrefix.__init__=prefix_init
    INSTALLED=True


def pytest_configure(config):install()

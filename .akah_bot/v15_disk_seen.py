"""Retain every native Harmonic deduplication key without an unbounded set.

Frozen consumer only uses membership/add; no trading iteration order changes.
Unknown key shapes migrate to a complete native set, preserving fallback
semantics rather than guessing at custom equality/hashing.
"""
from collections.abc import MutableSet
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from v15_resource_guard import ROOT
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError
from spotbot.research.multi_school_fidelity.integration_v13.harmonic_source import HarmonicSource

CURRENT=None
STORES={}
INSTALLED=False
ORIGINAL_INIT=HarmonicSource.__init__


def supported(key):
    return (type(key) is tuple and len(key)==2 and type(key[0]) is str and
            type(key[1]) is tuple and len(key[1])==4 and all(type(x) is str for x in key[1]))


def encode(key):
    return json.dumps(key,ensure_ascii=True,separators=(',',':'))


def digest(payload):return hashlib.sha256(payload.encode()).hexdigest()


class Store:
    def __init__(self,path=None):
        directory=ROOT/'.akah_bot/v15_runtime_spill';directory.mkdir(parents=True,exist_ok=True)
        if path is None:
            handle=tempfile.NamedTemporaryFile(prefix='seen-',suffix='.sqlite',dir=directory,delete=False)
            path=handle.name;handle.close()
        self.path=Path(path)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute('PRAGMA cache_size=-512')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE IF NOT EXISTS seen(ns INTEGER, key_sha TEXT, payload TEXT, PRIMARY KEY(ns,key_sha))')
        self.serial=self.connection.execute('SELECT COALESCE(MAX(ns),0) FROM seen').fetchone()[0]
        self.writes=0
    def commit(self):self.connection.commit()
    def close(self):
        if self.connection is not None:self.commit();self.connection.close();self.connection=None
    def __del__(self):
        try:self.close()
        except Exception:pass


class DiskSeen(MutableSet):
    def __init__(self,values=(),*,store=None):
        global CURRENT
        if store is None:
            if CURRENT is None:CURRENT=Store()
            store=CURRENT
        self.store=store;store.serial+=1;self.ns=store.serial;self.count=0;self.fallback=None
        self.update(values)
    def __len__(self):return len(self.fallback) if self.fallback is not None else self.count
    def _native_fallback(self):
        if self.fallback is None:self.fallback=set(iter(self))
    def __contains__(self,key):
        if self.fallback is not None:return key in self.fallback
        if not supported(key):self._native_fallback();return key in self.fallback
        payload=encode(key);h=digest(payload)
        row=self.store.connection.execute('SELECT payload FROM seen WHERE ns=? AND key_sha=?',(self.ns,h)).fetchone()
        if row is None:return False
        if digest(row[0])!=h or row[0]!=payload:raise ContractError('SEEN_ARCHIVE_CONTENT_OR_HASH_COLLISION')
        return True
    def __iter__(self):
        if self.fallback is not None:yield from self.fallback;return
        for h,payload in self.store.connection.execute('SELECT key_sha,payload FROM seen WHERE ns=? ORDER BY rowid',(self.ns,)):
            if digest(payload)!=h:raise ContractError('SEEN_ARCHIVE_CONTENT_DRIFT')
            item=json.loads(payload);key=(item[0],tuple(item[1]))
            if not supported(key) or encode(key)!=payload:raise ContractError('SEEN_ARCHIVE_SCHEMA_DRIFT')
            yield key
    def add(self,key):
        if self.fallback is not None:self.fallback.add(key);return
        if not supported(key):self._native_fallback();self.fallback.add(key);return
        if key in self:return
        payload=encode(key)
        self.store.connection.execute('INSERT INTO seen VALUES (?,?,?)',(self.ns,digest(payload),payload))
        self.count+=1;self.store.writes+=1
        if self.store.writes%1024==0:self.store.commit()
    def discard(self,key):
        if self.fallback is not None:self.fallback.discard(key);return
        if not supported(key):self._native_fallback();self.fallback.discard(key);return
        if key not in self:return
        self.store.connection.execute('DELETE FROM seen WHERE ns=? AND key_sha=?',(self.ns,digest(encode(key))))
        self.count-=1
    def update(self,values):
        for value in values:self.add(value)
    def clear(self):
        if self.fallback is not None:self.fallback.clear()
        self.store.connection.execute('DELETE FROM seen WHERE ns=?',(self.ns,));self.count=0
    def copy(self):return set(self)
    def __deepcopy__(self,memo):
        result=type(self)(store=self.store);memo[id(self)]=result
        if self.fallback is not None:result.fallback=copy.deepcopy(self.fallback,memo)
        else:result.update(self)
        return result


def restore_seen(path,ns,count):
    key=str(Path(path).resolve())
    if key not in STORES:
        directory=ROOT/'.akah_bot/v15_runtime_spill';directory.mkdir(parents=True,exist_ok=True)
        handle=tempfile.NamedTemporaryFile(prefix='resumed-seen-',suffix='.sqlite',dir=directory,delete=False)
        target=Path(handle.name);handle.close();shutil.copyfile(path,target)
        STORES[key]=Store(target)
    result=DiskSeen.__new__(DiskSeen);result.store=STORES[key]
    result.ns=ns;result.count=count;result.fallback=None
    result.store.serial=max(result.store.serial,ns)
    if result.store.connection.execute('SELECT COUNT(*) FROM seen WHERE ns=?',(ns,)).fetchone()[0]!=count:
        raise ContractError('SEEN_CHECKPOINT_ROW_COUNT_DRIFT')
    return result


def source_init(self,*args,**kwargs):
    ORIGINAL_INIT(self,*args,**kwargs)
    self.seen=DiskSeen(self.seen)


def migrate(provider):
    for sources in provider.sources.values():
        source=sources['harmonic']
        if type(source.seen) is set:source.seen=DiskSeen(source.seen)
        elif not isinstance(source.seen,DiskSeen):raise ContractError('UNKNOWN_SEEN_REPRESENTATION')


def install():
    global INSTALLED,ORIGINAL_INIT
    if not INSTALLED:
        ORIGINAL_INIT=HarmonicSource.__init__;HarmonicSource.__init__=source_init;INSTALLED=True

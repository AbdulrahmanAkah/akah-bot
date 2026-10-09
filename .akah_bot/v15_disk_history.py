"""All historical bars retained in exact file-backed numeric vectors.

No window shortening, eviction of source evidence, or lower precision. This
reduces private heap growth independently of the OS working-set/page cache.
"""
from array import array
from collections import OrderedDict
import mmap
from pathlib import Path
import shutil
import struct
import tempfile
import v15_bounded_storage as storage


class MappedVector:
    def __init__(self,code):
        self.code=code;self.length=0;self.capacity=512;self.item=struct.Struct('<'+code)
        directory=storage.ROOT/'.akah_bot/v15_runtime_spill'
        directory.mkdir(parents=True,exist_ok=True)
        handle=tempfile.NamedTemporaryFile(prefix='bars-',suffix='.bin',dir=directory,delete=False)
        self.path=Path(handle.name);handle.close()
        self.stream=self.path.open('r+b',buffering=0);self.stream.truncate(self.capacity*8)
        self.mapping=mmap.mmap(self.stream.fileno(),0,access=mmap.ACCESS_WRITE)
    def __len__(self):return self.length
    def __getitem__(self,index):
        if isinstance(index,slice):return array(self.code,(self[i] for i in range(*index.indices(self.length))))
        if index<0:index+=self.length
        if index<0 or index>=self.length:raise IndexError('array index out of range')
        return self.item.unpack_from(self.mapping,index*8)[0]
    def append(self,value):
        if self.length==self.capacity:
            self.mapping.flush();self.mapping.close()
            self.capacity+=512;self.stream.truncate(self.capacity*8)
            self.mapping=mmap.mmap(self.stream.fileno(),0,access=mmap.ACCESS_WRITE)
        self.item.pack_into(self.mapping,self.length*8,value);self.length+=1
    def extend(self,values):
        for value in values:self.append(value)
    def close(self):
        if getattr(self,'mapping',None) is not None:
            self.mapping.flush();self.mapping.close();self.mapping=None
        if getattr(self,'stream',None) is not None:self.stream.close();self.stream=None
    def __deepcopy__(self,memo):
        result=MappedVector(self.code);memo[id(self)]=result;result.extend(self);return result
    def __del__(self):
        try:self.close()
        except Exception:pass


def restore_vector(path,code,length,capacity):
    result=MappedVector.__new__(MappedVector)
    directory=storage.ROOT/'.akah_bot/v15_runtime_spill';directory.mkdir(parents=True,exist_ok=True)
    handle=tempfile.NamedTemporaryFile(prefix='resumed-bars-',suffix='.bin',dir=directory,delete=False)
    result.path=Path(handle.name);handle.close();shutil.copyfile(path,result.path)
    result.code=code;result.length=length;result.capacity=capacity;result.item=struct.Struct('<'+code)
    result.stream=result.path.open('r+b',buffering=0);result.mapping=mmap.mmap(result.stream.fileno(),0,access=mmap.ACCESS_WRITE)
    return result


class DiskPackedBars(storage.PackedBars):
    def __init__(self,degree):
        self.degree=degree;self.times=MappedVector('q');self.prices=MappedVector('d')
        self.fallback={};self.cache=OrderedDict()
    def _rebuild(self,values):
        self.times.close();self.prices.close()
        self.times=MappedVector('q');self.prices=MappedVector('d')
        self.fallback={};self.cache.clear()
        for value in values:self.append(value)


INSTALLED=False
def install():
    global INSTALLED
    if INSTALLED:return
    storage.install()
    # Storage's prefix constructor resolves this binding dynamically; no
    # tracked constructor or frozen source is edited.
    storage.PackedBars=DiskPackedBars
    INSTALLED=True

"""Crash-safe publication of a completed arm; no market execution or scoring."""
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import tempfile


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest().upper()


def json_file(path,value):
    def encode(x):return dataclasses.asdict(x) if dataclasses.is_dataclass(x) else str(x)
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,default=encode)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def bound(path,root):
    value=Path(path).resolve()
    if not value.is_relative_to(Path(root).resolve()):raise RuntimeError('OUTPUT_TRANSACTION_PATH_ESCAPE')
    return value


def prepare(staging,output,named_values,authority):
    staging=Path(staging).resolve();output=Path(output).resolve()
    staging.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='arm-publication-',dir=staging))
    rows=[]
    for name,value in named_values.items():
        if (Path(name).name!=name or name in {'','.', '..'} or not name.endswith('.json')):
            raise RuntimeError('EXACT_OUTPUT_BASENAME_REQUIRED')
        path=directory/name;json_file(path,value)
        rows.append({'staged_path':str(path),'final_path':str(output/name),'sha256':sha(path)})
    if not rows:raise RuntimeError('EMPTY_PUBLICATION_NOT_COMPLETE')
    intent=directory/'intent.json'
    json_file(intent,{'authority':authority,'outputs':rows,'status':'PREPARED_NOT_COMPLETE'})
    return {'path':str(intent),'sha256':sha(intent)}


def publish(binding,staging,output,authority,*,after_each=None):
    intent_path=bound(binding['path'],staging)
    if sha(intent_path)!=binding['sha256']:raise RuntimeError('PUBLICATION_INTENT_SHA_DRIFT')
    intent=json.loads(intent_path.read_text())
    if intent['authority']!=authority:raise RuntimeError('PUBLICATION_AUTHORITY_DRIFT')
    receipts=[]
    # Verify every recoverable artifact BEFORE any publication.
    for row in intent['outputs']:
        staged=bound(row['staged_path'],intent_path.parent)
        final=bound(row['final_path'],output)
        if final.exists():
            if sha(final)!=row['sha256']:raise RuntimeError('EXISTING_OUTPUT_DIFFERENT_NEVER_OVERWRITE')
        elif not staged.is_file() or sha(staged)!=row['sha256']:
            raise RuntimeError('STAGED_OUTPUT_MISSING_OR_DRIFT')
    for index,row in enumerate(intent['outputs']):
        staged=bound(row['staged_path'],intent_path.parent);final=bound(row['final_path'],output)
        if not final.exists():
            # Windows rename on this same-volume workspace refuses an existing
            # destination; unlike os.replace, it never overwrites a race.
            # Recovery accepts either the still-staged or published exact SHA.
            if os.name!='nt':raise RuntimeError('WINDOWS_EXCLUSIVE_RENAME_CONTRACT_REQUIRED')
            try:os.rename(staged,final)
            except FileExistsError:
                if sha(final)!=row['sha256']:raise RuntimeError('OUTPUT_PUBLICATION_RACE_DIFFERENT_CONTENT')
        if sha(final)!=row['sha256']:raise RuntimeError('PUBLISHED_OUTPUT_SHA_DRIFT')
        receipts.append({'path':str(final),'sha256':row['sha256']})
        if after_each is not None:after_each(index)
    # The caller may declare the arm complete only after this succeeds.
    return {'authority':authority,'outputs':receipts,'status':'ALL_ARM_OUTPUTS_EXACTLY_PUBLISHED',
            'intent_binding':binding}

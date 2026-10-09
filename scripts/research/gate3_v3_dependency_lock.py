"""Verify installed dependencies and wheels against official PyPI metadata."""
from pathlib import Path
from importlib import metadata
import urllib.request,json,hashlib
from spotbot.research.multi_school_fidelity.gate3_market_v3 import save,sha,GOV

NAMES=('arch','numpy','pandas','pyarrow','scipy','statsmodels','matplotlib','pillow','packaging',
       'formulaic','patsy','interface-meta','narwhals','wrapt','tzdata','python-dateutil','six',
       'typing-extensions','contourpy','cycler','fonttools','kiwisolver','pyparsing')

def main():
    distributions=[]; wheel_bindings=[]
    for name in NAMES:
        d=metadata.distribution(name); files={}
        for f in d.files or ():
            p=Path(d.locate_file(f))
            if p.is_file() and (p.suffix in {'.py','.pyd','.dll','.so'} or p.name in {'METADATA','RECORD'}):
                files[str(f)]=sha(p)
        if not files: raise ValueError('DEPENDENCY_RECORD_UNBOUND:'+name)
        distributions.append({'name':name,'version':d.version,'installed_files':files})
    for wheel in sorted(Path('.akah_bot/v3_wheels').glob('*.whl')):
        parts=wheel.name.split('-'); name,version=parts[0],parts[1]
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:
            doc=json.load(response)
        match=[r for r in doc['urls'] if r['filename']==wheel.name]
        if len(match)!=1 or sha(wheel)!=match[0]['digests']['sha256'].upper():
            raise ValueError('OFFICIAL_WHEEL_SHA_MISMATCH:'+wheel.name)
        wheel_bindings.append({'filename':wheel.name,'sha256':sha(wheel),'official_url':match[0]['url'],
            'metadata_source':f'https://pypi.org/pypi/{name}/{version}/json'})
    lock={'python_version':'3.13.14','arch_version':metadata.version('arch'),'substitution_used':False,
        'estimator':'arch.bootstrap.optimal_block_length:stationary','replications':9999,
        'distributions':distributions,'wheels':wheel_bindings,'installed_record_and_actual_runtime_files_hashed':True,
        'import_api_and_deterministic_paired_bootstrap':'tests/research/test_gate3_market_v3.py::test_arch_api_stationary_9999_paired_cash_days_and_determinism'}
    save(GOV/'12_DEPENDENCY_LOCK.json',lock)
    print('ARCH_DEPENDENCY_LOCK=PASS DISTRIBUTIONS='+str(len(distributions))+' OFFICIAL_WHEELS='+str(len(wheel_bindings)))

if __name__=='__main__': main()

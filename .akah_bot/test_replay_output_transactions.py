import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import replay_output_transactions as publication


class Tests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.akah_bot'
        self.root=Path(tempfile.mkdtemp(prefix='publication-fixture-',dir=root))
        self.stage=self.root/'stage';self.output=self.root/'output'
        self.authority={'task':'SYNTHETIC_ONLY','arm':'A|2X','frozen_sha':'A'*64}
        self.binding=publication.prepare(self.stage,self.output,
            {'A_2X.json':{'ledger':[1,2,3]},'A_2X_metrics.json':{'synthetic':True}},self.authority)
    def execute(self,**kwargs):return publication.publish(self.binding,self.stage,self.output,self.authority,**kwargs)
    def test_complete_and_idempotent_exact(self):
        first=self.execute();self.assertEqual(first,self.execute())
        self.assertEqual(len(first['outputs']),2)
    def test_interrupted_between_files_recovers_without_replay(self):
        def crash(index):
            if index==0:raise RuntimeError('INJECTED_CRASH_NOT_A_COMPLETED_ARM')
        with self.assertRaisesRegex(RuntimeError,'INJECTED_CRASH'):self.execute(after_each=crash)
        self.assertEqual(len(list(self.output.glob('*.json'))),1)
        result=self.execute();self.assertEqual(len(result['outputs']),2)
    def test_existing_different_output_never_overwritten(self):
        target=self.output/'A_2X.json';target.write_text('preserve-user-content')
        with self.assertRaisesRegex(RuntimeError,'NEVER_OVERWRITE'):self.execute()
        self.assertEqual(target.read_text(),'preserve-user-content')
    def test_stage_tamper_fails_before_any_publication(self):
        intent=json.loads(Path(self.binding['path']).read_text())
        Path(intent['outputs'][1]['staged_path']).write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'STAGED_OUTPUT'):self.execute()
        self.assertEqual(list(self.output.glob('*.json')),[])
    def test_authority_or_manifest_drift_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'AUTHORITY_DRIFT'):
            publication.publish(self.binding,self.stage,self.output,{'different':'authority'})
        Path(self.binding['path']).write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'INTENT_SHA_DRIFT'):self.execute()
    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'PATH_ESCAPE'):
            publication.publish(self.binding,self.stage/'wrong',self.output,self.authority)


if __name__=='__main__':
    program=unittest.main(exit=False);r=program.result
    root=Path(__file__).resolve().parents[1]
    (root/'.akah_bot/replay_output_transaction_unit_receipt.json').write_text(json.dumps({
        'status':'PASS' if r.wasSuccessful() else 'FAIL','tests':r.testsRun,
        'errors':len(r.errors),'failures':len(r.failures),
        'source_bindings':{p.name:hashlib.sha256(p.read_bytes()).hexdigest().upper()
                           for p in (Path(__file__),Path(publication.__file__))},
        'synthetic_only':True,'market_rows_read':0,'economic_replay_executed':False},indent=2)+'\n')
    raise SystemExit(not r.wasSuccessful())

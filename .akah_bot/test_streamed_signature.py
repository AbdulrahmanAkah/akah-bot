"""Exact digest-format test, no pandas, markets, or economic results."""
import ast
from collections import OrderedDict,Counter
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

tree=ast.parse((Path(__file__).parent/'profile_v15_full_scope.py').read_text())
namespace={'hashlib':hashlib,'json':json}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)
    and n.name=='streamed_signature'],type_ignores=[]),'<bound_signature>','exec'),namespace)

class Tests(unittest.TestCase):
    def test_exact_original_json_bytes_all_nodes_no_sampling(self):
        for count in (0,1,100):
            nodes=OrderedDict((str(i),SimpleNamespace(value=(i,'é\n'),origin='TEST')) for i in range(count))
            for queue,permission in (({},None),({'time':[]},('known','permission'))):
                diagnostics=Counter({'z':10,'a':3})
                original=hashlib.sha256(json.dumps((tuple(nodes.items()),queue,diagnostics,permission),
                    sort_keys=True,default=str).encode()).hexdigest()
                self.assertEqual(namespace['streamed_signature'](nodes,queue,diagnostics,permission),original)

if __name__=='__main__':unittest.main()

"""Existing bounded source-only probe with separate candidate report paths."""
from v15_resource_guard import ResourceGuard
guard = ResourceGuard('v15_point_index_full_source').start()
import ast
import inspect
import sys
import textwrap
import v15_point_query_index as candidate
import profile_v15_full_scope as probe
candidate.install()

source = textwrap.dedent(inspect.getsource(probe.main))
needle = "if '--native-epoch' in sys.argv:mode+='_native_epoch'"
if source.count(needle) != 1:
    raise RuntimeError('SOURCE_PROBE_OUTPUT_BINDING_DRIFT')
source = source.replace(needle, needle + "\n    mode += '_point_query_index'")
scope = dict(probe.__dict__)
exec(compile(ast.parse(source), __file__ + ':bounded-original-probe', 'exec'), scope)
try:
    scope['main']()
finally:
    guard.close()

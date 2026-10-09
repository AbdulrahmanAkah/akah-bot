"""Authenticate guard before importing pytest; synthetic-only validation."""
from v15_resource_guard import ResourceGuard
guard = ResourceGuard('v15_paged_synthetic').start()
import sys
import pytest
try:
    raise SystemExit(pytest.main(sys.argv[1:]))
finally: guard.close()

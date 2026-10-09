"""Explicit synthetic counter fixture. No market imports/rows/outcomes."""
import hashlib
import json
from pathlib import Path
import sys
import time
from v15_resource_guard import ResourceGuard


def main():
    guard=ResourceGuard('adaptive_guard_synthetic_fixture').start()
    values=[]
    for i in range(80):
        values.append((i,i*i));time.sleep(.05)
    result={'values':values,'sha256':hashlib.sha256(json.dumps(values).encode()).hexdigest(),
            'market_rows_read':0,'economic_replay_executed':False}
    Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n');guard.close()


if __name__=='__main__':main()

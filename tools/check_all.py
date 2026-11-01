#!/usr/bin/env python3
"""Run current and historical regression suites in isolated Python processes."""
import os
from pathlib import Path
import subprocess
import sys

def main():
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,MEETING_TEST_PLATFORM_ROOT=str(root))
    commands=[(root,[str(root/'tools/check_review.py')]),
              (root,[str(root/'tools/check_knowledge.py')]),
              (root,[str(root/'tools/check_traffic.py')]),
              (root,[str(root/'tools/check_recovery.py')]),
              (root,['-m','unittest','discover','-s','tests','-v']),
              (root/'monitoring',['-m','unittest','-v','test_monitor','test_telegram'])]
    failed=[]
    for cwd,args in commands:
        result=subprocess.run([sys.executable,*args],cwd=cwd,env=env)
        if result.returncode:failed.append(str(cwd))
    if failed:
        print('Failed suites:',', '.join(failed));return 1
    print('All offline suites passed. No live inference, notification, deployment or approval was performed.');return 0

if __name__=='__main__':raise SystemExit(main())

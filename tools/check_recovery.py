"""Offline recovery-tool safety checks; never use live data."""
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(root/'tools'),str(root/'review_tests'),str(root)]))
if __name__=='__main__':raise SystemExit(subprocess.run([sys.executable,'-m','unittest','-v','test_recovery_verifier'],cwd=root,env=env).returncode)

"""Synthetic waiting-only cancellation and monitoring checks."""
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(root),str(root/'review_tests'),str(root/'ingestion')]))
if __name__=='__main__':raise SystemExit(subprocess.run([sys.executable,'-m','unittest','-v','test_traffic_control'],cwd=root,env=env).returncode)

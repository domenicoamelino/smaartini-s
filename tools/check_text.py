"""Offline Text checks: synthetic drafts and fake Knowledge/Telegram only."""
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(root),str(root/'review_tests'),str(root/'ingestion')]))
if __name__=='__main__':
    raise SystemExit(subprocess.run([sys.executable,'-m','unittest','-v','test_text_backend','test_text_http','test_text_pipe','test_text_notices'],cwd=root,env=env).returncode)

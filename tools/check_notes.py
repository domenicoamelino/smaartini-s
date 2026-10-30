"""Offline Notes suite. Synthetic data, no real models, Telegram or Knowledge writes."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(root),str(root/'review_tests'),str(root/'ingestion')]))
    return subprocess.run([sys.executable,'-m','unittest','-v','test_notes_document','test_notes_backend',
        'test_notes_integration','test_notes_http','test_notes_risk','test_notes_notices',
        'test_notes_card','test_notes_pipe','test_shared_dashboard','test_notes_two_stage'],cwd=root,env=env).returncode


if __name__=='__main__':raise SystemExit(main())

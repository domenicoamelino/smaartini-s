#!/usr/bin/env python3
"""Current review-first workflow tests. No live models, notifications or approvals."""
import os
from pathlib import Path
import subprocess
import sys

def main():
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,MEETING_TEST_PLATFORM_ROOT=str(root),PYTHONPATH=os.pathsep.join([str(root/'review_tests'),str(root/'ingestion'),str(root)]))
    modules=['test_recap_resources','test_recap_deploy','test_recap_detail','test_document_recovery','test_flow','test_review','test_workflow','test_dashboard','test_speakers','test_pipe_review','test_report_quality','test_narrative_reliability','test_move_checkpoint','test_ingestion']
    return subprocess.run([sys.executable,'-m','unittest',*modules,'-v'],cwd=root,env=env).returncode

if __name__=='__main__':raise SystemExit(main())

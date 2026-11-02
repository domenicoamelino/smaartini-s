from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import meeting_review
import research_jobs as jobs
import traffic_control


class Traffic(unittest.TestCase):
    def test_research_visibility_owner_and_waiting_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jobs.init(root)
            with meeting_review.connection(root) as db:
                db.executescript('CREATE TABLE IF NOT EXISTS meetings(id TEXT,owner TEXT,folder TEXT); CREATE TABLE IF NOT EXISTS tasks(key TEXT,id TEXT,status TEXT,created REAL);')
            @contextmanager
            def connect():
                db=sqlite3.connect(root/'jobs.sqlite3');db.row_factory=sqlite3.Row
                try:
                    db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT,owner TEXT,state TEXT,detail TEXT,percent REAL,created REAL,updated REAL,filename TEXT,folder TEXT)')
                    yield db
                finally:db.close()
            worker=SimpleNamespace(ROOT=root,connect=connect)
            jid=jobs.submit(root,'alice','one','question','auto')
            jobs.submit(root,'bob','two','other private question','auto')
            with patch.dict('os.environ',{'SMARTINIS_RESEARCH_ENABLED':'1','SMARTINIS_NOTES_ENABLED':'0'}):
                result=traffic_control.snapshot(worker,'alice')
                self.assertEqual([r['id'] for r in result['jobs']],[jid])
                self.assertEqual(result['jobs'][0]['kind'],'research')
                self.assertNotIn('question',str(result))
                jobs.update(root,jid,'Waiting for query approval','needs_review',{'review':{}})
                result=traffic_control.snapshot(worker,'alice')
                self.assertEqual(result['jobs'][0]['status'],'needs_review')
                jobs.update(root,jid,'Queued','queued')
                traffic_control.cancel(worker,'alice','research',jid)
                self.assertEqual(jobs.get(root,'alice',jid)['status'],'cancelled')


if __name__=='__main__': unittest.main()

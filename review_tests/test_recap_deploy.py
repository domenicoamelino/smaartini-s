"""Synthetic deployment guard and code-only rollback; no real service operations."""
import contextlib,importlib.util,io,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

@unittest.skipUnless(os.name=='posix','Server deployment uses Linux file locking')
class DeployGuard(unittest.TestCase):
 def setUp(self):
  spec=importlib.util.spec_from_file_location('recap_deploy',Path(__file__).resolve().parents[1]/'deploy_recap_detail.py');self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.root=self.base/'meetings';self.root.mkdir();self.stage=self.base/'stage';self.stage.mkdir();self.target=self.base/'worker';self.target.mkdir()
  for file,tables in [('jobs.sqlite3',[('jobs','state')]),('reviews.sqlite3',[('tasks','status'),('notes_tasks','status')]),('research.sqlite3',[('research_jobs','status')])]:
   with sqlite3.connect(self.root/file) as db:
    for table,column in tables:db.execute('create table '+table+'('+column+' text)')
  for name in self.module.FILES:
   (self.target/name).write_text('original '+name);(self.stage/name).write_text('candidate '+name)
  self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  for key,value in {'BASE':self.base,'ROOT':self.root,'TARGET':self.target,'__file__':str(self.stage/'deploy_recap_detail.py'),'BEFORE':{n:self.module.sha(self.target/n) for n in self.module.FILES}}.items():self.stack.enter_context(patch.object(self.module,key,value))
  self.stack.enter_context(patch.object(self.module,'restart'))
  self.stack.enter_context(patch.object(self.module.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(b'{"worker_alive":true}')))
 def test_active_work_and_changed_production_refused(self):
  for name,table,column in [('jobs.sqlite3','jobs','state'),('reviews.sqlite3','tasks','status'),('research.sqlite3','research_jobs','status')]:
   with sqlite3.connect(self.root/name) as db:db.execute('insert into '+table+' values (?)',('queued',))
   with patch('sys.argv',['deploy']):
    with self.assertRaises(RuntimeError):self.module.main()
   self.module.restart.assert_not_called()
   with sqlite3.connect(self.root/name) as db:db.execute('delete from '+table)
  (self.target/self.module.FILES[0]).write_text('Uncommitted production edit')
  with patch('sys.argv',['deploy']):
   with self.assertRaises(AssertionError):self.module.main()
  self.module.restart.assert_not_called()
 def test_code_rollback_preserves_new_database_work(self):
  with patch('sys.argv',['deploy']),contextlib.redirect_stdout(io.StringIO()):self.module.main()
  backup=next((self.base/'backups').iterdir())
  for name in self.module.FILES:self.assertEqual((self.target/name).read_text(),'candidate '+name)
  with sqlite3.connect(self.root/'reviews.sqlite3') as db:db.execute("insert into tasks values ('completed')")
  # Deployment backup names are timestamped; advance the rollback timestamp.
  from datetime import datetime,timezone,timedelta
  future=datetime.now(timezone.utc)+timedelta(seconds=2)
  with patch('sys.argv',['deploy','--rollback',str(backup)]),patch.object(self.module.datetime,'datetime') as clock,contextlib.redirect_stdout(io.StringIO()):
   clock.now.return_value=future;self.module.main()
  for name in self.module.FILES:self.assertEqual((self.target/name).read_text(),'original '+name)
  with sqlite3.connect(self.root/'reviews.sqlite3') as db:self.assertEqual(db.execute('select status from tasks').fetchall(),[('completed',)])

if __name__=='__main__':unittest.main()

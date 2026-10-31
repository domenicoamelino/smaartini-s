import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import meeting_notifications as notifications
import text_store as store
import text_ingestion
from test_text_backend import VALUE

class TextNotices(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);store.init(self.root)
        self.home=self.root/'monitor';self.home.mkdir()
        (self.home/'meeting-notifications.json').write_text(json.dumps({'enabled':True,'owner_chats':{'alice':123},'openwebui_url':'https://text.invalid'}))
        (self.home/'telegram_notify.py').write_text('import json\nfrom pathlib import Path\ndef read_token(path):return "fixture"\ndef api(token,method,payload):Path(__file__).with_name("delivered.json").write_text(json.dumps(payload))\n')
        jid=store.submit(self.root,'alice','one',VALUE);store.act(self.root,jid,'alice',{'action':'approve','revision':1,'acknowledge_review':True})
        self.doc=store.approved_document(store.folder(self.root,jid),self.root,'alice')
    def tearDown(self):self.tmp.cleanup()
    def test_successful_ingestion_notice_routes_to_text_once(self):
        text_ingestion.notify(self.root,self.doc,'kb');text_ingestion.notify(self.root,self.doc,'kb')
        with patch.dict(os.environ,{'MEETING_MONITOR_HOME':str(self.home),'SMARTINIS_TEXT_ENABLED':'1'}):
            self.assertTrue(notifications.deliver_next(self.root));self.assertFalse(notifications.deliver_next(self.root))
        value=json.loads((self.home/'delivered.json').read_text());self.assertEqual(value['chat_id'],123)
        self.assertIn('successfully ingested',value['text']);self.assertIn('/meeting-ui/dashboard/?view=text#',value['text'])
    def test_disabled_text_holds_pending_notification(self):
        text_ingestion.notify(self.root,self.doc,'kb')
        with patch.dict(os.environ,{'MEETING_MONITOR_HOME':str(self.home),'SMARTINIS_TEXT_ENABLED':'0'}):self.assertFalse(notifications.deliver_next(self.root))
        self.assertFalse((self.home/'delivered.json').exists())
    def test_no_notification_just_from_save_or_approval(self):
        with store.connection(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM notices').fetchone()[0],0)

if __name__=='__main__':unittest.main()

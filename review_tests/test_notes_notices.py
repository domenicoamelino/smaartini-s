import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import meeting_notifications as notifications
import meeting_review as review
import notes_store as notes


class Notices(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);notes.init(self.root)
        self.home=self.root/'monitor';self.home.mkdir()
        (self.home/'meeting-notifications.json').write_text(json.dumps({'enabled':True,
            'owner_chats':{'alice':123},'openwebui_url':'https://notes.invalid'}))
        (self.home/'telegram_notify.py').write_text(
            'import json\nfrom pathlib import Path\ndef read_token(path):return "fixture"\n'
            'def api(token,method,payload):Path(__file__).with_name("delivered.json").write_text(json.dumps(payload))\n')
        review.notice(self.root,'note-test','alice','note-'+'a'*32,'Notes draft ready for review')
    def tearDown(self):self.tmp.cleanup()
    def test_notes_delivery_disabled_with_feature(self):
        with patch.dict(os.environ,{'MEETING_MONITOR_HOME':str(self.home),'SMARTINIS_NOTES_ENABLED':'0'}):
            self.assertFalse(notifications.deliver_next(self.root))
        self.assertFalse((self.home/'delivered.json').exists())
    def test_notes_reuses_owner_binding_and_notes_link_once(self):
        with patch.dict(os.environ,{'MEETING_MONITOR_HOME':str(self.home),'SMARTINIS_NOTES_ENABLED':'1'}):
            self.assertTrue(notifications.deliver_next(self.root));self.assertFalse(notifications.deliver_next(self.root))
        delivered=json.loads((self.home/'delivered.json').read_text())
        self.assertEqual(delivered['chat_id'],123)
        self.assertIn('/meeting-ui/notes/#note-',delivered['text'])
        self.assertNotIn('/meeting-ui/dashboard/',delivered['text'])


if __name__=='__main__':unittest.main()

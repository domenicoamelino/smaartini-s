from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest

import knowledge_lifecycle as lifecycle
import research_knowledge
import text_store


class Knowledge(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); text_store.init(self.root)
        self.jid=text_store.submit(self.root,'alice','one',{'title':'Synthetic JCA recap','date':'2026-10-01','markdown':'JCA compatibility testing is unresolved.'})
        self.ledger=self.root/'ledger.json'
        self.entry={'file_id':'fixture-id','indexed_at':1,'approval_revision':1,'approval_sha256':'unknown'}
        self.save()
    def save(self):
        self.ledger.write_text(json.dumps({'destination':{'meetings_root':str(self.root)},'meetings':{self.jid:{'committed':self.entry}}}))
    def approve(self):
        text_store.act(self.root,self.jid,'alice',{'action':'approve','revision':1,'acknowledge_review':True})
        doc=text_store.approved_document(self.root/self.jid,self.root,'alice')
        self.entry['approval_sha256']=doc['approval_sha256']; self.save()
    def query(self,owner='alice'):
        return research_knowledge.retrieve(self.root,self.ledger,owner,'latest JCA technical risks')
    def test_draft_index_owner_and_immutable_approval(self):
        self.assertEqual(self.query(),[])
        self.approve(); self.assertEqual(len(self.query()),1)
        self.assertEqual(self.query('bob'),[])
        self.entry.pop('file_id');self.save();self.assertEqual(self.query(),[])
    def test_pending_and_removed_knowledge_excluded(self):
        self.approve()
        lifecycle.change(self.root,self.jid,'alice','remove',0)
        self.assertEqual(self.query(),[])
        lifecycle.finish(self.root,self.jid,'alice',1)
        self.assertEqual(self.query(),[])
    def test_hash_tampering_refused(self):
        self.approve()
        (self.root/self.jid/'approved/r000001/knowledge.md').write_text('tampered JCA')
        with self.assertRaises(ValueError): self.query()
    def test_new_draft_does_not_override_indexed_approved_revision(self):
        self.approve()
        text_store.act(self.root,self.jid,'alice',{'action':'save','revision':1,'payload':{'title':'Other draft','date':'2026-10-02','markdown':'New unapproved secret'}})
        result=self.query(); self.assertEqual(result[0]['revision'],1)
        self.assertNotIn('New unapproved secret',result[0]['text'])
    def test_unrelated_new_discussion_does_not_match_named_project(self):
        self.approve()
        other=text_store.submit(self.root,'alice','two',{'title':'Unrelated','date':'2026-10-02','markdown':'Technical risks and current industry practices for another project.'})
        text_store.act(self.root,other,'alice',{'action':'approve','revision':1,'acknowledge_review':True})
        doc=text_store.approved_document(self.root/other,self.root,'alice')
        ledger=json.loads(self.ledger.read_text())
        ledger['meetings'][other]={'committed':{**self.entry,'indexed_at':2,'approval_sha256':doc['approval_sha256']}}
        self.ledger.write_text(json.dumps(ledger))
        self.assertEqual([r['key'] for r in self.query()],[self.jid])


if __name__=='__main__': unittest.main()

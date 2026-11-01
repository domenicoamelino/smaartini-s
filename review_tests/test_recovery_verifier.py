import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import verify_recovery as recovery

class RecoverySafety(unittest.TestCase):
    def fixture(self,root,symlink=False):
        backup=root/'backup';backup.mkdir();raw=b'fixture'
        with tarfile.open(backup/'recovery.tar.gz','w:gz') as archive:
            item=tarfile.TarInfo('archive/source')
            if symlink:item.type=tarfile.SYMTYPE;item.linkname='../../escape'
            else:item.size=len(raw)
            archive.addfile(item,None if symlink else io.BytesIO(raw))
        manifest={'files':{'archive/source':hashlib.sha256(raw).hexdigest()}}
        (backup/'MANIFEST.json').write_text(json.dumps(manifest))
        (backup/'TRANSFER.json').write_text(json.dumps({'manifest_sha256':recovery.digest(backup/'MANIFEST.json'),'bundle_sha256':recovery.digest(backup/'recovery.tar.gz')}))
        return backup
    def test_paths_are_confined(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ['../escape','/absolute','C:/escape','a\\b']:
                with self.assertRaises(ValueError):recovery.safe(folder,name)
            self.assertEqual(recovery.safe(folder,'archive/source'),Path(folder)/'archive/source')
    def test_corrupt_transfer_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);backup=self.fixture(root)
            with (backup/'recovery.tar.gz').open('ab') as handle:handle.write(b'corrupt')
            with self.assertRaisesRegex(ValueError,'transfer hash'):recovery.verify(backup,root/'restore',True)
            self.assertFalse((root/'restore').exists())
    def test_link_member_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);backup=self.fixture(root,True)
            with self.assertRaisesRegex(ValueError,'Non-regular'):recovery.verify(backup,root/'restore',True)
            self.assertFalse((root/'restore').exists())
    def test_existing_restore_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);backup=self.fixture(root);restore=root/'restore';restore.mkdir();sentinel=restore/'keep';sentinel.write_text('retained')
            with self.assertRaisesRegex(ValueError,'fresh isolated'):recovery.verify(backup,restore,True)
            self.assertEqual(sentinel.read_text(),'retained')

if __name__=='__main__':unittest.main()

import time
import unittest
from research_bounds import bounded


class Bounds(unittest.TestCase):
    def test_kills_stalled_stage(self):
        start=time.monotonic()
        with self.assertRaises(TimeoutError): bounded(time.sleep,(20,),0.2)
        self.assertLess(time.monotonic()-start,5)
    def test_success(self): self.assertEqual(bounded(str,(123,),3),'123')


if __name__=='__main__': unittest.main()

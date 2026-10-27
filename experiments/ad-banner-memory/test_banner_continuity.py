import unittest
import numpy as np
from banner_continuity import BannerMemory

class BannerSafety(unittest.TestCase):
 def setUp(self):
  self.image=np.random.default_rng(71).integers(0,256,(270,480,3),dtype=np.uint8)
  self.memory=BannerMemory()
 def test_requires_confirmed_clean_teacher(self):
  self.memory.seed(self.image,0,'A',False,True);self.memory.seed(self.image,0,'A',True,False)
  self.assertFalse(self.memory.query(self.image,1,'A'))
 def test_matches_unchanged_strip_with_different_program_area(self):
  self.memory.seed(self.image,0,'A',True,True);other=self.image.copy();other[:235]=0
  self.assertTrue(self.memory.query(other,1,'A'))
 def test_channel_or_app_session_change_clears(self):
  self.memory.seed(self.image,0,'A',True,True)
  self.assertFalse(self.memory.query(self.image,1,'B'));self.assertEqual([],self.memory.anchors)
 def test_expiry_cannot_be_extended_by_candidate(self):
  self.memory.seed(self.image,0,'A',True,True)
  for now in [10,50,100,120]:self.assertTrue(self.memory.query(self.image,now,'A'))
  self.assertFalse(self.memory.query(self.image,120.001,'A'))
 def test_future_anchor_rejected(self):
  self.memory.seed(self.image,10,'A',True,True);self.assertFalse(self.memory.query(self.image,9,'A'))
 def test_flat_and_corner_logo_rejected(self):
  for value in [0,128,255]:
   flat=np.full((270,480,3),value,dtype=np.uint8);self.assertFalse(self.memory.useful(self.memory.patch(flat)))
  corner=np.zeros_like(self.image);corner[240:268,430:470]=self.image[240:268,430:470]
  self.assertFalse(self.memory.useful(self.memory.patch(corner)))
 def test_delayed_response_not_available_early(self):
  self.memory.seed(self.image,0,'A',True,True,available_at=2)
  self.assertFalse(self.memory.query(self.image,1,'A'))
  self.assertTrue(self.memory.query(self.image,2,'A'))
 def test_stale_teacher_rejected(self):
  self.memory.seed(self.image,0,'A',True,True,available_at=8.001)
  self.assertFalse(self.memory.query(self.image,9,'A'))
 def test_metadata_only_navigation_away_and_back_clears(self):
  self.memory.query(self.image,0,'A');self.memory.seed(self.image,0,'A',True,True)
  self.memory.advance(1,'B');self.memory.advance(2,'A')
  self.assertFalse(self.memory.query(self.image,3,'A'))
 def test_capacity_bounded(self):
  for i in range(100):self.memory.seed(self.image,i,'A',True,True)
  self.assertEqual(32,len(self.memory.anchors))

if __name__=='__main__':unittest.main()

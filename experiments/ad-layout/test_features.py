import unittest
import numpy as np
from features import extract

class FeaturesTest(unittest.TestCase):
 def test_uniform_frames_are_finite(self):
  for value in (0,127,255):
   v,flat=extract(np.full((270,480,3),value,dtype=np.uint8))
   self.assertEqual(v.shape,(141,));self.assertTrue(np.isfinite(v).all());self.assertGreater(flat,.99)
 def test_sponsored_region_cannot_leak_into_model(self):
  image=np.random.default_rng(17).integers(0,256,(270,480,3),dtype=np.uint8)
  modified=image.copy();modified[17:44,12:92]=255
  np.testing.assert_array_equal(extract(image)[0],extract(modified)[0])
 def test_wrong_dimensions_rejected(self):
  with self.assertRaises(ValueError):extract(np.zeros((100,100,3),dtype=np.uint8))
if __name__=='__main__':unittest.main()

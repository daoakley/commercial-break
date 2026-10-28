import importlib.util,json,sys,tempfile,unittest,zipfile,base64,hashlib,urllib.parse
from pathlib import Path
import xml.etree.ElementTree as ET
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from cryptography.x509.oid import NameOID
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,widget_signer

class BuildChecks(unittest.TestCase):
 def test_refuses_placeholders_and_bad_tokens(self):
  d=json.loads((ROOT/'device.example.json').read_text())
  with self.assertRaises(ValueError):build.validate_device(d)
  d={'identity':{'psid':'test-identity','vdvendorcode':'test-vendor','modelID':'test-model','sourceInfo':'1'},'parameters':{'api':2,'zipcode':'test-region','firmware':'test-firmware','modelID':'test-model'}}
  self.assertIs(build.validate_device(d),d)
  d['controlToken']='bad';self.assertRaises(ValueError,build.validate_device,d)
  d['controlToken']='a'*64;build.validate_device(d)
  d['parameters']['api']=1;self.assertRaises(ValueError,build.validate_device,d)
 def test_original_icon_is_valid_png(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'icon.png';build.icon(p);self.assertTrue(p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
 def test_signature_covers_file_bytes(self):
  key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
  name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Ephemeral test certificate')]);now=datetime.now(timezone.utc)
  cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).sign(key,hashes.SHA256())
  files=[('config.xml',b'<widget/>'),('service/main.js',b'console.log("test");')]
  for role in ['AuthorSignature','DistributorSignature']:
   blob=widget_signer._signature(role,files,key,[cert]);xml=ET.fromstring(blob);ns={'d':widget_signer.DSIG}
   info=xml.find('d:SignedInfo',ns);refs=info.findall('d:Reference',ns)
   self.assertEqual(len(refs),len(files)+1)
   for ref,(name,data) in zip(refs,files):
    self.assertEqual(urllib.parse.unquote(ref.attrib['URI']),name)
    self.assertEqual(base64.b64decode(ref.find('d:DigestValue',ns).text),hashlib.sha512(data).digest())
   digest=refs[-1].find('d:DigestValue',ns).text
   signature=base64.b64decode(xml.find('d:SignatureValue',ns).text)
   cert.public_key().verify(signature,widget_signer._signed_info(files,digest,True).encode(),padding.PKCS1v15(),hashes.SHA512())
   with self.assertRaises(Exception):cert.public_key().verify(signature,b'tampered',padding.PKCS1v15(),hashes.SHA512())
if __name__=='__main__':unittest.main()

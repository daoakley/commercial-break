"""Make a temporary copy of the TV's own capture allowlist library.

No firmware or installed system library is modified. This version-specific
patch replaces the existing /usr/bin/tzcapturesample allowlist entry with
/usr/bin/dotnet and pads the unused bytes with NULs.
"""

from pathlib import Path
import argparse
import hashlib

OLD = b"/usr/bin/tzcapturesample\x00"
NEW = b"/usr/bin/dotnet\x00"
TESTED_SHA256 = "fdd3d6f58d2fc73fed6c07bc9d431c86ac911f34930b68071a65a141ab55970d"

parser = argparse.ArgumentParser()
parser.add_argument("original", type=Path, help="unmodified libtzcapturec.so copied from this TV")
parser.add_argument("output", type=Path, help="temporary patched copy")
args = parser.parse_args()
data = args.original.read_bytes()
if hashlib.sha256(data).hexdigest() != TESTED_SHA256:
    raise SystemExit("Library differs from the tested Frame 1720.7 copy; refusing to patch")
if data.count(OLD) != 1:
    raise SystemExit("Expected allowlist entry is absent or ambiguous; refusing to patch")
args.output.write_bytes(data.replace(OLD, NEW.ljust(len(OLD), b"\x00"), 1))
print(args.output)

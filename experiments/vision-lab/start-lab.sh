#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
base=$(CDPATH= cd -- "$here/../.." && pwd)
private="$base/work/commercial-vision-lab/private"
umask 077
mkdir -p "$private"
python3 - "$private" <<'PY'
import secrets,sys
from pathlib import Path
p=Path(sys.argv[1]);p.chmod(0o700)
for name in ('lab-token','feed-token'):
    f=p/name
    if not f.exists():f.write_text(secrets.token_urlsafe(32))
    f.chmod(0o600)
(p/'lab.env').write_text('LAB_TOKEN='+(p/'lab-token').read_text().strip()+'\n')
(p/'lab.env').chmod(0o600)
(p/'upload.curl').write_text('header = "Authorization: Bearer '+(p/'feed-token').read_text().strip()+'"\n')
(p/'upload.curl').chmod(0o600)
PY
export LAB_ENV_FILE="$private/lab.env"
exec docker compose -p commercial-vision-lab -f "$here/compose.yaml" up -d --build

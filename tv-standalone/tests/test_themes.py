"""Verify artwork can render offline within the TV overlay's limits."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
entries = json.loads((root/'engine/themes/catalog.json').read_text())
assert len(entries) == 15
assert json.loads((root/'engine/themes/default.json').read_text()) == json.loads((root/'engine/scene.json').read_text())
for t in entries:
    scene = json.loads((root/'engine/themes'/f"{t['id']}.json").read_text())
    objects = scene['objects']
    assert 1 <= len(objects) <= 256
    b = objects[0]
    assert b['type'] == 'rectangle' and [b[k] for k in ('x','y','width','height')] == [0,0,1920,1080]
    assert b['color'].endswith('FF')
    for o in objects:
        assert o['type'] in ('rectangle','ellipse','line','polygon','textblock')
        assert len(o['color']) == 9 and o['color'][0] == '#'
        if o['type'] == 'polygon': assert 3 <= len(o['points']) <= 128
    assert len(json.dumps(scene)) < 1024*1024
print('15 offline scene catalogs validated; Original preserved.')

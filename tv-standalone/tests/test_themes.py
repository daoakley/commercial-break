"""Verify artwork can render offline within the TV overlay's limits."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
entries = json.loads((root/'engine/themes/catalog.json').read_text())
assert len(entries) == 23
assert json.loads((root/'engine/themes/default.json').read_text()) == json.loads((root/'engine/scene.json').read_text())
for t in entries:
    scene = json.loads((root/'engine/themes'/f"{t['id']}.json").read_text())
    assert t['id']=='default' or scene['infoMode']=='clock'
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
print('23 offline scene catalogs validated; Original preserved.')

# A modern browser silently accepted inset; the target TV did not.
css = (root/'app/appearance.css').read_text()
assert 'inset:' not in css
for edge in ('top:0','right:0','bottom:0','left:0'):
    assert edge in css.split('#appearance-panel{',1)[1].split('}',1)[0]
print('Legacy TV full-screen positioning uses explicit edges.')

ids={t['id'] for t in entries}
for city in ('raleigh','memphis','dc','charlotte'):
    for phase in ('day','night'): assert city+'-'+phase in ids
print('Four city skylines have paired day/night themes; custom artwork is clock-only.')

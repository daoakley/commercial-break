"""Offline parser regression tests. Never connects to a TV or recognition server."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def response(kind='AD'):
    candidate = {'vid': 123, 'source': 4, 'content': {'type': kind, 'ccType': kind}}
    return {'result': {'acr': {
        'result_frames': [{'matching': True, 'dist': 2, 'tvt': {'utc': '1000'},
                           'main': candidate, 'multi': []}],
        'recog_content': {'matching': True, 'tvt': {'utc': '1000'},
                          'main': candidate, 'multi': [],
                          'confidence': {'tvt': {'utc': '1000'},
                                         'cc': [{'vid': 123, 'source': 4, 'keepCnt': 0}]}}
    }}}


cases = []
def add(name, r, expected, at='1000'):
    cases.append((name, {'response': r, 'at': at}, expected))

add('explicit current-frame ad', response(), 'ad')
add('broadcast program is not ad proof', response('PROGRAM'), 'uncertain')
add('stale timestamp', response(), 'uncertain', '2000')
add('malformed response', {}, 'uncertain')
r = response(); r['result']['acr']['result_frames'][0]['dist'] = 45
add('weak match rejected', r, 'uncertain')
r = response(); r['result']['acr']['recog_content']['matching'] = False
add('aggregate match absent', r, 'uncertain')
r = response(); r['result']['acr']['result_frames'][0]['main'] = {'vid': 999, 'source': 2, 'content': {'type': 'PROGRAM'}}
add('current commercial-confidence ad', r, 'ad')
s = copy.deepcopy(r); s['result']['acr']['recog_content']['confidence']['cc'][0]['keepCnt'] = 1
add('retained confidence rejected', s, 'uncertain')
s = copy.deepcopy(r); s['result']['acr']['recog_content']['confidence']['tvt']['utc'] = '900'
add('stale confidence rejected', s, 'uncertain')
s = copy.deepcopy(r); s['result']['acr']['recog_content']['confidence']['cc'][0]['vid'] = 456
add('unassociated confidence rejected', s, 'uncertain')
s = copy.deepcopy(r); s['result']['acr']['recog_content']['confidence']['cc'][0]['source'] = 2
add('wrong confidence source rejected', s, 'uncertain')
s = copy.deepcopy(r); f = copy.deepcopy(s['result']['acr']['result_frames'][0]); f['tvt']['utc'] = '900'; f['dist'] = 50; s['result']['acr']['result_frames'].append(f)
add('mixed-timestamp confidence rejected', s, 'uncertain')

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'cases.json'
    path.write_text(json.dumps([c[1] for c in cases]))
    result = subprocess.run([sys.argv[1] if len(sys.argv)>1 else 'dotnet',
                             str(root/'engine/bin/Release/netcoreapp3.1/CommercialBlock.dll'),
                             '--replay', str(path)], check=True, text=True, capture_output=True,
                            env=dict(os.environ, DOTNET_ROLL_FORWARD='Major'))
    actual = result.stdout.splitlines()
    assert len(actual)==len(cases), result.stderr
    for (name, _, wanted), got in zip(cases, actual):
        assert got==wanted, (name,wanted,got)
    print(f'{len(cases)} verdict safety tests passed')

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
FAKE_BUSCTL = '''#!/usr/bin/env python3
import os, pathlib, sys
p = pathlib.Path(os.environ['FAKE_SETTINGS'])
values = dict(line.split('=') for line in p.read_text().splitlines())
args = sys.argv[1:]
method = next((x for x in args if x in ('GetBacklight', 'GetPictureMode', 'SetBacklight')), '')
if method == 'SetBacklight':
    values['active'] = args[-2]
    p.write_text(''.join(f'{k}={v}\\n' for k, v in values.items()))
    print('i 0')
elif method == 'GetBacklight':
    if values.get('fail_read') == '1':
        sys.exit(1)
    print('ii', values['active' if args[-1] == '0' else 'saved'], '0')
elif method == 'GetPictureMode':
    print('ii', values['mode' if args[-1] == '0' else 'saved_mode'], '0')
else:
    sys.exit(2)
'''


class BacklightSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.settings = self.folder / 'settings'
        self.settings.write_text('active=38\nsaved=38\nmode=65538\nsaved_mode=65538\n')
        self.fake = self.folder / 'busctl'
        self.fake.write_text(FAKE_BUSCTL)
        self.fake.chmod(0o755)
        self.env = os.environ | {
            'STATE_DIR': str(self.folder),
            'BACKLIGHT_BUSCTL': str(self.fake),
            'FAKE_SETTINGS': str(self.settings),
        }

    def run_shell(self, command):
        script = f'. "{HERE / "tv-backlight.sh"}"; {command}'
        result = subprocess.run(['/bin/sh', '-c', script], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def value(self, key):
        return dict(line.split('=') for line in self.settings.read_text().splitlines())[key]

    def set_value(self, key, value):
        values = dict(line.split('=') for line in self.settings.read_text().splitlines())
        values[key] = value
        self.settings.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))

    def test_dim_only_active_setting_and_restore(self):
        self.run_shell('dim_for_ad 20')
        self.assertEqual(self.value('active'), '20')
        self.assertEqual(self.value('saved'), '38')
        self.assertTrue((self.folder / 'owned-backlight').exists())
        self.run_shell('release_owned_backlight')
        self.assertEqual(self.value('active'), '38')
        self.assertFalse((self.folder / 'owned-backlight').exists())

    def test_viewer_adjustment_is_not_overwritten_or_redimmed(self):
        self.run_shell('dim_for_ad 20')
        self.set_value('active', '30')
        self.run_shell('dim_for_ad 20; release_owned_backlight')
        self.assertEqual(self.value('active'), '30')
        self.assertTrue((self.folder / 'backlight-override').exists())

    def test_failed_read_preserves_restore_marker(self):
        self.run_shell('dim_for_ad 20')
        self.set_value('fail_read', '1')
        self.run_shell('release_owned_backlight || true')
        self.assertTrue((self.folder / 'owned-backlight').exists())
        self.set_value('fail_read', '0')
        self.run_shell('release_owned_backlight')
        self.assertEqual(self.value('active'), '38')

    def test_skips_when_active_differs_from_saved(self):
        self.set_value('saved', '35')
        self.run_shell('dim_for_ad 20 || true')
        self.assertEqual(self.value('active'), '38')
        self.assertFalse((self.folder / 'owned-backlight').exists())


if __name__ == '__main__':
    unittest.main()

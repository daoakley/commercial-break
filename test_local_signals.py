import json
from pathlib import Path
import struct
import subprocess
import unittest
import zlib

from local_signals import audio_features, own_card, visual_features


def png(rows):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 480, 270, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(b'\0' + row for row in rows))) + chunk(b'IEND', b''))


class LocalSignalsTests(unittest.TestCase):
    def test_black_screen_is_not_our_card_but_exact_project_mask_is(self):
        rows = [bytearray(480 * 3) for _ in range(270)]
        self.assertFalse(own_card(visual_features(png(rows))))
        mask = json.loads(Path(__file__).with_name('cover_mask.json').read_text())['mask']
        for i, on in enumerate(mask):
            if on:
                y, x = 108 + (i // 110) * 2, 130 + (i % 110) * 2
                rows[y][x * 3:x * 3 + 3] = b'\xff\xff\xff'
        self.assertTrue(own_card(visual_features(png(rows))))
        # Rich information stays inside fixed margins, below the title mask.
        for y in range(190, 240):
            rows[y][75 * 3:405 * 3] = b'\x90' * (330 * 3)
        self.assertTrue(own_card(visual_features(png(rows))))
        # The same glyphs over ordinary video must not conceal real evidence.
        rows[:80] = [bytearray(b'\xc0' * 1440) for _ in range(80)]
        self.assertFalse(own_card(visual_features(png(rows))))

    def test_audio_invalid_size_and_gap_inputs_are_bounded(self):
        for data in (b'', b'\0' * 3, b'\0' * (48000 * 4 * 3 + 4)):
            with self.assertRaises(ValueError): audio_features(data)
        result = audio_features(b'\0' * 48000 * 4)
        self.assertEqual(result['silence_fraction'], 1)
        self.assertFalse(result['controls_mute'])

    def test_tv_cycle_schedule_is_portable_and_never_negative(self):
        # Execute the shipped expression with the system awk: this caught a
        # real printf/ternary parsing failure that shell syntax checks missed.
        text = Path(__file__).with_name('tv-agent.sh').read_text()
        expression = text.split('delay=$(awk', 1)[1].split("'", 2)[1]
        for start, end, target, expected in [(100, 100.5, 1, .5), (100, 102, 1, .1), (100, 101, 4, 3)]:
            value = subprocess.check_output(['awk', '-v', f'a={start}', '-v', f'b={end}', '-v', f'n={target}', expression], text=True)
            self.assertAlmostEqual(float(value), expected)


if __name__ == '__main__': unittest.main()

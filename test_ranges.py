import unittest
from ranges import byte_range


class RangeTests(unittest.TestCase):
    def test_playback_and_seeking(self):
        for header, expected in [(None, (0, 999)), ('bytes=0-', (0, 999)),
                                 ('bytes=500-599', (500, 599)), ('bytes=-100', (900, 999)),
                                 ('bytes=900-2000', (900, 999)), ('bytes=-2000', (0, 999))]:
            with self.subTest(header=header):
                self.assertEqual(byte_range(header, 1000), expected)

    def test_invalid_ranges(self):
        for header in ['bytes=1000-', 'bytes=10-5', 'bytes=-0', 'bytes=-',
                       'bytes=0-1,5-6', 'wrong']:
            with self.subTest(header=header), self.assertRaises(ValueError):
                byte_range(header, 1000)


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from mlg import render, sfx


class IntensityTests(unittest.TestCase):
    def setUp(self):
        # Keep real sprites and compositing; remove slow audio decoding/synthesis.
        sounds = patch.object(sfx, "load", return_value=np.full(128, 0.1, np.float32))
        drop = patch.object(sfx, "dubstep_drop", return_value=(np.zeros(2 * sfx.SR), 0.5))
        whoosh = patch.object(sfx, "whoosh", return_value=np.zeros(128, np.float32))
        sounds.start()
        drop.start()
        whoosh.start()
        self.addCleanup(sounds.stop)
        self.addCleanup(drop.stop)
        self.addCleanup(whoosh.stop)

    def make(self, **options):
        return render.MLG(320, 180, 30, 2, (0.5, 0.5), 420, **options)

    def test_normal_preserves_default_frames_and_audio(self):
        default = self.make()
        normal = self.make(intensity="normal")
        src = Image.new("RGB", (320, 180), (50, 80, 100))
        for t in (0, default.M + 0.05, default.R0 + 0.65, default.D + 0.4,
                  default.E + 0.8, default.W + 0.9, default.DW + 0.5):
            np.testing.assert_array_equal(default.frame(src, t), normal.frame(src, t))
        np.testing.assert_array_equal(default.audio(np.zeros(0)), normal.audio(np.zeros(0)))
        self.assertEqual(len(normal.particles), 38)
        self.assertEqual(len(normal.hits), 10 + 8 + 4)

    def test_presets_change_density_and_flash_strength_without_changing_timing(self):
        models = [self.make(intensity=level) for level in ("low", "normal", "chaos")]
        low, normal, chaos = models
        self.assertLess(len(low.particles), len(normal.particles))
        self.assertLess(len(normal.particles), len(chaos.particles))
        self.assertLess(len(low.hits), len(normal.hits))
        self.assertLess(len(normal.hits), len(chaos.hits))
        self.assertEqual(low.total, normal.total)
        self.assertEqual(normal.total, chaos.total)
        src = Image.new("RGB", (320, 180), (50, 80, 100))
        means = [np.asarray(m.frame(src, m.M + 0.05)).mean() for m in models]
        self.assertLess(means[0], means[1])
        self.assertLess(means[1], means[2])
        for m in models:
            self.assertEqual(m.frame(src, m.D + 0.4).size, src.size)

    def test_intensity_respects_disabled_sections(self):
        for level in ("low", "normal", "chaos"):
            with self.subTest(level=level):
                m = self.make(intensity=level, weed=False, illuminati=False,
                              deal_with_it=False, drop_enabled=False, replays=False)
                self.assertEqual(m.particles, [])
                self.assertFalse(m.joint)
                self.assertEqual(m.snares, [])
                self.assertAlmostEqual(m.total, 2 + render.FIRST)


if __name__ == "__main__":
    unittest.main()

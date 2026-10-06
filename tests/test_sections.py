"""Section combinations must produce continuous timelines and matching audio/visuals."""

import itertools
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from mlg import render, sfx


class SectionTests(unittest.TestCase):
    def test_all_section_combinations(self):
        # Distinct short tones identify each outro; all other audio is silent.
        levels = {"illuminati": 0.1, "smoke_weed_everyday": 0.2, "deal_with_it": 0.3}

        def sound(slot, fallback):
            return np.full(int(0.1 * sfx.SR), levels.get(slot, 0), np.float32)

        src = Image.new("RGB", (320, 180), (30, 60, 90))
        for values in itertools.product((False, True), repeat=5):
            options = dict(zip(("weed", "deal_with_it", "illuminati", "replays", "drop_enabled"), values))
            with self.subTest(**options), patch.object(sfx, "load", side_effect=sound), \
                    patch.object(sfx, "dubstep_drop", return_value=(np.zeros(2 * sfx.SR), 0.5)):
                m = render.MLG(320, 180, 30, 2, (0.5, 0.5), 420, **options)
                expected = (2 + render.FIRST
                            + (render.DROP_GAP + 2 if options["drop_enabled"] else 0)
                            + (2 * render.REPLAY_LEN if options["replays"] else 0)
                            + (render.ILLUM_LEN if options["illuminati"] else 0)
                            + (render.WEED_LEN if options["weed"] else 0)
                            + (render.DEAL_LEN if options["deal_with_it"] else 0))
                self.assertAlmostEqual(m.total, expected)
                self.assertEqual(len(m.shots), 3 if options["replays"] else 1)
                self.assertEqual(m.replay(m.R0 + 0.2) is not None, options["replays"])
                audio = m.audio(np.zeros(0, np.float32))
                self.assertEqual(len(audio), int(m.total * sfx.SR))
                tail = np.zeros_like(audio)
                for enabled, at, level in ((options["illuminati"], m.E, 0.1),
                                           (options["weed"], m.W, 0.2),
                                           (options["deal_with_it"], m.DW, 0.3)):
                    if enabled:
                        i = int(at * sfx.SR)
                        tail[i:i + int(0.1 * sfx.SR)] = np.tanh(1.3 * level)
                np.testing.assert_allclose(audio[int(m.E * sfx.SR):], tail[int(m.E * sfx.SR):], atol=1e-7)
                # Check every transition, including collapsed outro boundaries.
                for t in sorted({0, m.M, m.R0, m.D, m.E, m.W, m.DW, m.total - 1 / 30}):
                    if t >= m.total:
                        continue
                    with patch.object(m, "paste", wraps=m.paste) as paste:
                        self.assertEqual(m.frame(src, t).size, src.size)
                        drawn = [call.args[1] for call in paste.call_args_list]
                        if not options["deal_with_it"]:
                            self.assertFalse(any(sprite is m.shades or sprite is m.obey or sprite is m.thug
                                                 for sprite in drawn))
                        if not options["illuminati"]:
                            self.assertFalse(any(sprite is m.eye for sprite in drawn))
                if not options["weed"]:
                    self.assertFalse(m.joint)
                    self.assertTrue(all(p.t0 < m.E for p in m.particles))
                if not options["drop_enabled"]:
                    self.assertEqual(m.D, m.E)
                    self.assertEqual(m.hits, [st + 0.1 * i for st in m.shots
                                             for i in range(4 if st == m.M else 3)])
                    self.assertEqual(m.snares, [])



if __name__ == "__main__":
    unittest.main()

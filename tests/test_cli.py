import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from mlg import render


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "demo/target_practice.mp4"


class ValidationTests(unittest.TestCase):
    def test_invalid_arguments_exit_before_rendering(self):
        for args in (("--target", "2,0.5"), ("--target", "0.5"),
                     ("--target", "nan,0"), ("--bpm", "0"), ("--bpm", "inf"),
                     ("--drop-len", "-1"), ("--drop-start", "-1"),
                     ("--moment", "-1"), ("--width", "1"),
                     ("--drop", "track.mp3", "--no-drop")):
            with self.subTest(args=args), patch.object(render, "probe") as probe:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
                    render.main([str(SOURCE), *args])
                self.assertEqual(result.exception.code, 2)
                self.assertIn("error:", stderr.getvalue())
                probe.assert_not_called()

    def test_missing_file_and_input_overwrite(self):
        for args in ((str(ROOT / "missing.mp4"),), (str(SOURCE), "-o", str(SOURCE))):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as result:
                render.main(args)
            self.assertEqual(result.exception.code, 2)

    def test_missing_ffmpeg(self):
        with patch.object(render.shutil, "which", return_value=None), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            render.main([str(SOURCE)])
        self.assertEqual(result.exception.code, 2)

    def test_moment_beyond_video(self):
        info = {"w": 320, "h": 180, "fps": 30, "duration": 2, "has_audio": False}
        with patch.object(render, "probe", return_value=info), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            render.main([str(SOURCE), "-m", "3"])
        self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from mlg import render, sfx


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "color=c=navy:s=320x180:r=10:d=2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(self.source)], check=True)
        self.drop = self.root / "short.wav"
        with wave.open(str(self.drop), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sfx.SR)
            audio.writeframes(b"\x00\x10" * int(0.05 * sfx.SR))
        self.args = [str(self.source), "-m", "0.7", "--width", "320",
                     "--drop", str(self.drop), "--no-weed", "--no-deal-with-it",
                     "--no-illuminati", "--no-replays"]

    def invoke(self, extra=(), error_code=None):
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            if error_code is None:
                render.main([*self.args, *extra])
            else:
                with self.assertRaises(SystemExit) as result:
                    render.main([*self.args, *extra])
                self.assertEqual(result.exception.code, error_code)
        self.assertFalse(list(self.root.glob(".mlg-*")))
        self.assertNotIn("Traceback", log.getvalue())
        if error_code is not None:
            self.assertNotIn("done ->", log.getvalue())
        return log.getvalue()

    def test_short_drop_and_streamable_output(self):
        out = self.root / "result.mp4"
        self.invoke(("-o", str(out)))
        self.assertGreater(render.probe(out)["duration"], 1)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "null", "-"], check=True)
        atoms = []
        with out.open("rb") as stream:
            while header := stream.read(8):
                size, name = struct.unpack(">I4s", header)
                atoms.append(name)
                if size == 0:
                    break
                header_size = 8
                if size == 1:
                    size = struct.unpack(">Q", stream.read(8))[0]
                    header_size = 16
                stream.seek(size - header_size, 1)
        self.assertLess(atoms.index(b"moov"), atoms.index(b"mdat"))

    def test_encoder_failure_preserves_existing_output(self):
        out = self.root / "result.invalid"
        out.write_bytes(b"previous output")
        message = self.invoke(("-o", str(out)), error_code=1)
        self.assertIn("video encoding failed", message)
        self.assertEqual(out.read_bytes(), b"previous output")

    def test_render_exception_cleans_up(self):
        out = self.root / "result.mp4"
        with patch.object(render.MLG, "frame", side_effect=RuntimeError("test frame failure")):
            self.assertIn("test frame failure", self.invoke(("-o", str(out)), error_code=1))
        self.assertFalse(out.exists())

    def test_cancelled_render_cleans_up(self):
        out = self.root / "result.mp4"
        with patch.object(render.MLG, "frame", side_effect=KeyboardInterrupt):
            self.assertIn("cancelled", self.invoke(("-o", str(out)), error_code=130))
        self.assertFalse(out.exists())

    def test_audio_only_input_and_empty_drop(self):
        self.args[0] = str(self.drop)
        self.assertIn("no video stream", self.invoke(error_code=2))
        self.args[0] = str(self.source)
        self.assertIn("no audio", self.invoke(("--drop-start", "10"), error_code=1))


class DecoderTests(unittest.TestCase):
    def test_empty_or_failed_decoder(self):
        for code in (0, 1):
            with self.subTest(code=code), patch.object(render.subprocess, "Popen") as popen:
                proc = popen.return_value
                proc.stdout.read.return_value = b""
                proc.wait.return_value = code
                reader = render.FrameReader("unused.mp4", 320, 180, 30)
                try:
                    with self.assertRaisesRegex(RuntimeError, "decoding failed|no decodable frames"):
                        reader.get(0)
                finally:
                    reader.close()
                proc.stdout.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

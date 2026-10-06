"""Run with the wheel's Python, outside the checkout, to verify packaged data."""

from pathlib import Path

from mlg import sfx, sprites

checkout = Path(__file__).resolve().parents[1]
assert not sprites.ASSETS_DIR.is_relative_to(checkout), "imported checkout instead of wheel"
assert (sprites.ASSETS_DIR / "doritos.png").is_file()
assert len(sprites.load_frames("snoop")) == 44
assert len(sprites.load_quickscope(180)[1]) == 24
assert sfx.find_sound("airhorn").is_file()
assert len(sfx.load("airhorn", lambda: None)) > 0
assert not (sprites.ASSETS_DIR / "raw").exists()
assert not (sfx.SOUNDS_DIR / "raw").exists()
print("Installed wheel assets, sounds, and animations OK")

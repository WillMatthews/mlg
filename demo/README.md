# MLG demo

`demo_MLG.mp4` is a 720p, 30fps demo made with the MLG renderer and its bundled
meme assets, soundbites, and synthesized dubstep drop. The original arcade target
animation is `target_practice.mp4`; the hit lands at 3.2 seconds in the centre.

Recreate from the repository root:

```sh
uv run python demo/make_source.py
uv run mlg demo/target_practice.mp4 -o demo/demo_MLG.mp4 -m 3.2 --target 0.5,0.5 --width 1280 --seed 420
```

If NumPy and Pillow are already installed, you can also use `python3` for the
source generator and `python3 -m mlg.render` in place of `uv run mlg`.

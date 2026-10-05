# major-league-gaming

MLG-ify a clip: quickscope → hitmarkers + airhorn → deep-fried dubstep drop
(Illuminati, Doritos, Mtn Dew, Snoop, Sanic, frog, MOM GET THE CAMERA, OH BABY A TRIPLE,
DAMN SON, WOMBO COMBO) → ILLUMINATI CONFIRMED → SMOKE WEED EVERYDAY → DEAL WITH IT.
First-person MW2 Intervention quickscope (keyed from the classic green screen, needs
`yt-dlp`), the real MW2 sniper reticle texture and the meme-standard hitmarker.

    uv run mlg clip.mp4                   # -> clip_MLG.mp4
    uv run mlg clip.mp4 -m 4.2 --target 0.4,0.3
    uv run mlg clip.mp4 --drop bangarang.mp3 --drop-start 31.5 --bpm 110

- `-m` big-moment time (default: loudest point); `--target` scope aim / shades landing point.
- Any `sounds/<slot>.{mp3,wav,...}` overrides the procedural synth for that slot:
  airhorn, hitmarker, sniper, mom_get_the_camera, oh_baby_a_triple, wow,
  smoke_weed_everyday, deal_with_it, drop.
- Any `assets/<slot>.png` overrides the drawn sprite: doritos, mtn_dew, illuminati,
  doge, weed, shades, thug_life, intervention, mlg_logo, obey, hitmarker, scope, lens_flare,
  sanic, joint; `assets/snoop/`, `assets/frog/` and `assets/quickscope/` hold animated frames.
  `uv run python -m mlg.prep` rebuilds them from `assets/raw/`.
- The processed `assets/` and `sounds/` are committed, so a fresh clone just works.
  `./fetch_assets.sh` re-downloads the originals into `assets/raw/` + `sounds/raw/`
  (gitignored) and rebuilds them; the quickscope green screen needs `yt-dlp`.
- Credits: soundbites from myinstants.com; images from pngimg.com, pngkey.com,
  pngitem.com, tenor.com; MW2 sniper reticle from the Call of Duty wiki; quickscope
  green screen from YouTube `xVrayfJ_oI8`. All third-party meme material, used for parody.
- The drop isn't fetched: bring your own track as `sounds/drop.mp3` or `--drop`,
  else a synthesised 140bpm wobble drop is used.

#!/usr/bin/env bash
# Fetch the classic MLG soundbites + images. Everything lands in sounds/ and
# assets/ (both gitignored: third-party meme material, personal use only).
# Any sounds/<slot>.* or assets/<slot>.png overrides the procedural fallback.
# The drop (Skrillex etc.) is not fetched: put your own copy at sounds/drop.mp3.
set -euo pipefail
cd "$(dirname "$0")"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
mkdir -p sounds assets/raw

get() {  # get <dest> <url> [referer]
  [ -s "$1" ] && return 0
  echo "fetching $1"
  curl -sfL -A "$UA" -H "Accept: image/png,image/*;q=0.9,*/*;q=0.8" ${3:+-e "$3"} -o "$1" "$2"
}

while read -r slot src; do
  get "sounds/$slot.mp3" "https://www.myinstants.com/media/sounds/$src"
done <<'LIST'
airhorn airhorn.mp3
hitmarker hitmarker_2.mp3
sniper mlg-sound-effect-intervention-mw2.mp3
mom_get_the_camera mom-get-the-camera.mp3
oh_baby_a_triple oh_baby_a_triple.mp3
wow wow-mlg-sound-effect.mp3
deal_with_it deal-with-it.mp3
smoke_weed_everyday snoop-dogg-smoke-weed-everyday.mp3
get_rekt get-rekt.mp3
damn_son damn-son-whered-you-find-this_2.mp3
illuminati xfilestheme.mp3
oh_my_god omg-ooohh.mp3
wombo_combo wombo-combo-excited.mp3
LIST

cut() {  # cut <slot> <myinstants file> <start> <duration>: a soundbite from inside a longer clip
  [ -s "sounds/$1.mp3" ] && return 0
  mkdir -p sounds/raw
  get "sounds/raw/$2" "https://www.myinstants.com/media/sounds/$2"
  ffmpeg -v error -y -ss "$3" -t "$4" -i "sounds/raw/$2" \
    -af "afade=t=in:d=0.02,afade=t=out:st=$(awk "BEGIN{print $4-0.35}"):d=0.35" "sounds/$1.mp3"
}
cut smash_ohh wombo-combo_1.mp3 1.5 2.4          # Melee commentators: "OH! OH! OHHHH!"
cut crowd_ohh the-rap-battle-parody-oh.mp3 0 2.5  # crowd "OHHHHHH!"

while read -r slot url; do
  ext="${url%%\?*}"; ext="${ext##*.}"; [[ "$ext" == */* ]] && ext=png  # e.g. wiki .../x.png/revision/latest
  get "assets/raw/$slot.$ext" "$url" "$(echo "$url" | cut -d/ -f1-3)/"  # hotlink referer
done <<'LIST'
doritos https://pngimg.com/uploads/doritos/doritos_PNG2.png
illuminati https://www.pngkey.com/png/full/0-5965_i-sick-illuminati-mlg-illuminati-confirmed.png
doge https://pngimg.com/uploads/doge_meme/doge_meme_PNG7.png
weed https://pngimg.com/uploads/cannabis/cannabis_PNG11.png
shades https://pngimg.com/uploads/thug_life/thug_life_PNG40.png
thug_life https://pngimg.com/uploads/thug_life/thug_life_PNG29.png
mtn_dew https://www.pngkey.com/png/full/7-75610_free-png-mountain-dew-png-images-transparent-mountain.png
intervention https://www.pngkey.com/png/full/153-1533952_intervention-3rd-person-mw2-intervention-sniper-rifle-png.png
mlg_logo https://www.pngkey.com/png/full/40-403391_transparent-mlg-logo-png.png
obey https://www.pngkey.com/png/full/365-3654840_thug-life-clipart-transparent-obey-hat-png.png
scope https://static.wikia.nocookie.net/callofduty/images/5/56/Default_sniper_scope_reticle.png/revision/latest?cb=20101008131509&format=original
joint https://www.pngkey.com/png/full/108-1080506_lit-blunt-png-mlg-blunt-png.png
hitmarker https://www.pngitem.com/pimgs/b/84-844941_hitmarker-png-transparent.png
lens_flare https://www.pngkey.com/png/full/1-11886_miscellaneous-yellow-lens-flare-png.png
sanic https://www.pngkey.com/png/full/149-1491309_sanic-gotta-go-fast.png
frog https://media1.tenor.com/m/4oJSY3cZxksAAAAC/dancing-frogy.gif
snoop https://media1.tenor.com/m/L8YYzotEahEAAAAC/snoopdog-hiphop.gif
LIST

# Genuine MW2 Intervention quickscope green screen (first-person raise / scope / bolt cycle).
if [ ! -s assets/raw/quickscope.mp4 ]; then
  if command -v yt-dlp >/dev/null; then
    echo "fetching assets/raw/quickscope.mp4"
    yt-dlp -q -f "bv*[height<=720][ext=mp4]/bv*[height<=720]" -o assets/raw/quickscope.mp4 \
      "https://www.youtube.com/watch?v=xVrayfJ_oI8"
  else
    echo "yt-dlp not installed: skipping the quickscope green screen (falls back to scope-only)"
  fi
fi

uv run python -m mlg.prep

#!/bin/sh
set -eu
name="$1"
dir="${OUT_DIR:-recordings}"
start="${START:-5}"
ffmpeg -loglevel error -y -ss "$start" -i "$dir/$name.webm" -c:v libx264 -pix_fmt yuv420p -crf 22 "$dir/$name.mp4"
ffmpeg -loglevel error -y -ss "$start" -i "$dir/$name.webm" \
  -vf "fps=8,crop=1460:640:230:230,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=none" \
  "$dir/$name.gif"
ls -lh "$dir/$name.mp4" "$dir/$name.gif"

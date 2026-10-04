#!/bin/sh
# `chiron walls update`: download or update the wallpaper collection (github.com/dharmx/walls, about
# 3.5 GB) into ~/Pictures/walls, skipping the videos in animated/. Runs as the desktop user.
# The collection is for personal use only and is never redistributed (see rice/wallsets.conf).
set -eu
DEST="$HOME/Pictures/walls"
URL=https://github.com/dharmx/walls.git

if [ -d "$DEST/.git" ]; then
  echo "Updating $DEST …"
  git -C "$DEST" pull --ff-only --depth 1
else
  echo "Downloading the wallpaper collection to $DEST (about 3.5 GB; this takes a while) …"
  mkdir -p "$(dirname "$DEST")"
  # Partial clone + sparse checkout: only the files we keep are downloaded
  git clone --filter=blob:none --no-checkout --depth 1 "$URL" "$DEST"
  git -C "$DEST" sparse-checkout set --no-cone '/*' '!/animated/'
  git -C "$DEST" checkout
fi
echo "Size: $(du -sh --exclude=.git "$DEST" | cut -f1) in $(find "$DEST" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | wc -l) categories"
/opt/chiron/rice/chiron-rice thumbs
echo "Done. Pick one with Super+W (or: chiron rice pick)."

#!/bin/sh
src="$(cd "$(dirname "$0")" && pwd)/custom_components/dreame_airpurifier"
dst="$HOME/.config/homeassistant/custom_components/dreame_airpurifier"
sudo cp -r "$src" "$dst"
echo "Copied $src → $dst"

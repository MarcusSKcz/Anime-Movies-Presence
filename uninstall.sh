#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/.local/share/mpv-discord-presence"
BIN="$HOME/.local/bin/mpv-presence"
MPV_SCRIPT="${XDG_CONFIG_HOME:-$HOME/.config}/mpv/scripts/discord_presence.lua"
MPV_CLEAR_SCRIPT="${XDG_CONFIG_HOME:-$HOME/.config}/mpv/scripts/discord_presence_clear.lua"
SYSTEMD_SERVICE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/mpv-presence.service"

systemctl --user disable --now mpv-presence.service 2>/dev/null || true
rm -f "$SYSTEMD_SERVICE" "$MPV_SCRIPT" "$MPV_CLEAR_SCRIPT" "$BIN"
rm -rf "$APP_DIR"
systemctl --user daemon-reload 2>/dev/null || true

echo 'Uninstalled program files. Config/cache kept under ~/.config/mpv-presence and ~/.cache/mpv-presence.'

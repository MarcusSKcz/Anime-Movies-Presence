#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/mpv-discord-presence"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mpv-presence"
MPV_SCRIPT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mpv/scripts"
MPV_OPTS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mpv/script-opts"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$APP_DIR" "$BIN_DIR" "$CONFIG_DIR" "$MPV_SCRIPT_DIR" "$MPV_OPTS_DIR" "$SYSTEMD_USER_DIR"

rsync -a --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  "$ROOT_DIR/" "$APP_DIR/"

python -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

ln -sf "$APP_DIR/mpv/discord_presence.lua" "$MPV_SCRIPT_DIR/discord_presence.lua"
ln -sf "$APP_DIR/mpv/discord_presence_clear.lua" "$MPV_SCRIPT_DIR/discord_presence_clear.lua"
cp -n "$APP_DIR/mpv/discord_presence.conf.example" "$MPV_OPTS_DIR/discord_presence.conf" || true

cat > "$BIN_DIR/mpv-presence" <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/.venv/bin/python" -m mpv_presence "\$@"
EOF
chmod +x "$BIN_DIR/mpv-presence"

cat > "$SYSTEMD_USER_DIR/mpv-presence.service" <<EOF
[Unit]
Description=MPV Discord Rich Presence daemon
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m mpv_presence
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

"$BIN_DIR/mpv-presence" --init
systemctl --user daemon-reload
systemctl --user enable --now mpv-presence.service

echo
printf 'Installed. Now edit: %s/config.json\n' "$CONFIG_DIR"
echo 'Set discord.client_id and metadata.tmdb_api_key. Optional: metadata.rpdb_api_key.'
echo 'Then run: systemctl --user restart mpv-presence.service'
echo 'Logs: journalctl --user -u mpv-presence.service -f'

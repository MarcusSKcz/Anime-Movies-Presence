# mpv-discord-presence

A local MPV → Discord Rich Presence bridge for anime, movies, and TV.

It is built for Linux/mpv setups like CachyOS + mpv-anime-build, but it should work with normal mpv too because it uses the standard mpv Lua script directory.

## What it does

- Shows what you are watching in Discord Rich Presence.
- Uses Discord **Watching** activity where supported by your pypresence version.
- Shows a poster/cover as the large image.
- Uses Discord timestamps for playback progress.
- Detects pause/play and clears presence when playback ends.
- Parses anime releases with `aniparse` first.
- Parses movie/TV filenames with `guessit`.
- Resolves anime metadata through AniList.
- Resolves movie/TV metadata through TMDB.
- Uses RPDB posters when you provide an RPDB key, otherwise falls back to AniList/TMDB covers.
- Supports Slovak/Czech/English TMDB search fallback.
- Supports manual overrides for cursed filenames.
- Has privacy ignore paths/patterns.
- Caches API lookups locally.

## Files

```text
mpv-discord-presence/
├── install.sh
├── uninstall.sh
├── requirements.txt
├── mpv/
│   ├── discord_presence.lua
│   └── discord_presence.conf.example
├── mpv_presence/
│   ├── daemon.py
│   ├── parsing.py
│   ├── providers.py
│   ├── presence.py
│   └── ...
└── examples/
    └── overrides.json
```

## Install on CachyOS / Arch

You need Python, curl, and rsync:

```bash
sudo pacman -S python python-pip curl rsync
```

Then from this folder:

```bash
./install.sh
```

The installer will:

- copy the app to `~/.local/share/mpv-discord-presence`
- create a venv
- install Python dependencies
- symlink the mpv Lua script into `~/.config/mpv/scripts/`
- create and enable a user systemd service
- create default config files in `~/.config/mpv-presence/`

## Configure

Open:

```bash
nano ~/.config/mpv-presence/config.json
```

Set at least:

```json
{
  "discord": {
    "client_id": "YOUR_DISCORD_APPLICATION_ID"
  },
  "metadata": {
    "tmdb_api_key": "YOUR_TMDB_V3_API_KEY",
    "rpdb_api_key": "OPTIONAL_RPDB_KEY"
  }
}
```

AniList does not need an API key for public metadata lookups.

After editing config:

```bash
systemctl --user restart mpv-presence.service
```

Logs:

```bash
journalctl --user -u mpv-presence.service -f
```

Status check:

```bash
mpv-presence --status
```

## Discord app setup

1. Go to the Discord Developer Portal.
2. Create an application.
3. Copy the Application ID / Client ID.
4. Put it in `discord.client_id`.
5. Keep Discord desktop running while testing.

External cover URLs should work with current Discord Rich Presence, but if Discord ever changes behavior, you can set `discord.large_image_fallback` to an uploaded asset key in your Discord app.

## TMDB setup

1. Make a TMDB account.
2. Get a v3 API key.
3. Put it in `metadata.tmdb_api_key`.

The plugin searches TMDB in this order by default:

```json
["sk-SK", "cs-CZ", "en-US"]
```

This helps files like:

```text
Harry Potter a Väzeň z Azkabanu SK Dabing 1080p.mkv
Temný rytier CZ 1080p.mkv
Rýchlo a zbesilo 5 SK.mkv
```

## RPDB setup

RPDB is optional.

If you add `metadata.rpdb_api_key`, the plugin will use RPDB posters for TMDB-resolved movies/TV shows:

```json
"poster_priority": ["rpdb", "metadata"]
```

If RPDB does not have a poster, `fallback=true` is included in the generated RPDB URL.

## Overrides

Open:

```bash
nano ~/.config/mpv-presence/overrides.json
```

Example:

```json
{
  "overrides": [
    {
      "contains": "Temny rytier",
      "type": "movie",
      "title": "The Dark Knight",
      "tmdb_id": 155
    },
    {
      "contains": "Frieren",
      "type": "anime",
      "title": "Frieren: Beyond Journey's End",
      "anilist_id": 154587,
      "season": 1
    }
  ]
}
```

Supported match fields:

- `contains`
- `filename_contains`
- `path_contains`
- `glob`
- `regex`

Supported forced metadata fields:

- `type`: `anime`, `movie`, or `tv`
- `title`
- `search_title`
- `year`
- `season`
- `episode`
- `episode_title`
- `tmdb_id`
- `anilist_id`
- `mal_id`

Restart after changing overrides:

```bash
systemctl --user restart mpv-presence.service
```

## Privacy rules

Default config ignores paths/patterns containing:

```json
["private", "nsfw", "hentai", "18+"]
```

Add your own:

```json
"privacy": {
  "ignore_paths": [
    "/home/overlord/Private",
    "/mnt/storage/private"
  ],
  "ignore_patterns": [
    "private",
    "nsfw",
    "hentai",
    "18+"
  ]
}
```

When ignored, the daemon clears Discord presence.

## MPV script options

The installer copies this file:

```bash
~/.config/mpv/script-opts/discord_presence.conf
```

You normally do not need to edit it. If you enable a server token in config, set the same token there.

## Testing without mpv

With the daemon running:

```bash
curl -X POST http://127.0.0.1:47230/mpv \
  -H 'Content-Type: application/json' \
  -d '{
    "action":"play",
    "path":"/anime/Frieren/[SubsPlease] Sousou no Frieren - 04 (1080p).mkv",
    "filename":"[SubsPlease] Sousou no Frieren - 04 (1080p).mkv",
    "duration":1440,
    "position":120,
    "pause":false
  }'
```

Clear:

```bash
curl -X POST http://127.0.0.1:47230/mpv \
  -H 'Content-Type: application/json' \
  -d '{"action":"end"}'
```

## Troubleshooting

### Discord presence does not show

Check:

```bash
journalctl --user -u mpv-presence.service -f
```

Common causes:

- Discord desktop is not running.
- `discord.client_id` is missing or wrong.
- Discord activity sharing is disabled.
- Your Discord client needs a restart.

### Metadata does not match

Use `overrides.json` for weird filenames, Slovak/Czech titles, anime season weirdness, or files with no year.

### Posters do not show

The plugin passes external image URLs to Discord. This should work on current Discord, but if it fails, try:

- use normal TMDB/AniList poster fallback by removing your RPDB key
- upload one fallback image in the Discord Developer Portal and set `discord.large_image_fallback`
- check that the poster URL opens in your browser

### mpv-anime-build

It should work the same as normal mpv as long as it loads scripts from:

```bash
~/.config/mpv/scripts/
```

## Uninstall

```bash
./uninstall.sh
```

Config/cache are intentionally kept. Remove manually if desired:

```bash
rm -rf ~/.config/mpv-presence ~/.cache/mpv-presence ~/.local/state/mpv-presence
```
## Attribution

Personal non-commercial mpv Discord Rich Presence project using AniList and TMDB metadata.

This product uses the TMDB API but is not endorsed or certified by TMDB.


-- Extra reliable MPV shutdown hook for clearing Discord Rich Presence.
-- Install to: ~/.config/mpv/scripts/discord_presence_clear.lua

local endpoint = "http://127.0.0.1:47230/mpv"

local function clear_presence()
    mp.command_native({
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        capture_stderr = true,
        args = {
            "curl", "-sS",
            "--max-time", "1",
            "-H", "Content-Type: application/json",
            "-d", '{"action":"shutdown"}',
            endpoint
        }
    })
end

mp.register_event("shutdown", clear_presence)

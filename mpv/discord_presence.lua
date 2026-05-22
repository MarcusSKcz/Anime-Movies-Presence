-- MPV -> local Discord Rich Presence daemon hook
-- Install to: ~/.config/mpv/scripts/discord_presence.lua

local utils = require "mp.utils"
local msg = require "mp.msg"

local o = {
    host = "127.0.0.1",
    port = "47230",
    token = "",
    update_interval = 15,
    curl_timeout = 1.5,
}

local options = require "mp.options"
options.read_options(o, "discord_presence")

local endpoint = "http://" .. o.host .. ":" .. o.port .. "/mpv"
local timer = nil
local last_path = nil

local function collect(action)
    return {
        action = action,
        path = mp.get_property("path") or "",
        filename = mp.get_property("filename") or "",
        media_title = mp.get_property("media-title") or "",
        duration = mp.get_property_number("duration", 0) or 0,
        position = mp.get_property_number("time-pos", 0) or 0,
        pause = mp.get_property_bool("pause", false) or false,
        playlist_pos = mp.get_property_number("playlist-pos", -1),
        chapter = mp.get_property("chapter-metadata/title") or ""
    }
end

local function post(action)
    local path = mp.get_property("path")
    if not path and action ~= "shutdown" and action ~= "end" then
        return
    end

    local payload = utils.format_json(collect(action))
    local args = {
        "curl", "-sS",
        "--max-time", tostring(o.curl_timeout),
        "-H", "Content-Type: application/json",
    }

    if o.token ~= nil and o.token ~= "" then
        table.insert(args, "-H")
        table.insert(args, "X-MPV-Presence-Token: " .. o.token)
    end

    table.insert(args, "-d")
    table.insert(args, payload)
    table.insert(args, endpoint)

    mp.command_native_async({
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        capture_stderr = true,
        args = args
    }, function(success, result, error)
        if not success then
            msg.debug("Discord presence daemon unavailable: " .. tostring(error))
        elseif result and result.status and result.status >= 400 then
            msg.warn("Discord presence daemon returned HTTP error")
        end
    end)
end

local function ensure_timer()
    if timer == nil then
        timer = mp.add_periodic_timer(o.update_interval, function()
            post("update")
        end)
    end
    timer:resume()
end

mp.register_event("file-loaded", function()
    last_path = mp.get_property("path")
    ensure_timer()
    mp.add_timeout(0.5, function()
        post("play")
    end)
end)

mp.observe_property("pause", "bool", function(_, paused)
    if mp.get_property("path") then
        post(paused and "pause" or "play")
    end
end)

mp.observe_property("time-pos", "number", function()
    -- no-op: timer handles progress, this just wakes the script in some MPV builds
end)

mp.register_event("end-file", function()
    if timer ~= nil then
        timer:kill()
    end
    if last_path ~= nil then
        post("end")
        last_path = nil
    end
end)

mp.register_event("shutdown", function()
    post("shutdown")
end)

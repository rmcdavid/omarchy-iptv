-- Omarchy IPTV: add to ~/.config/hypr/bindings.lua
-- SUPER + SHIFT + T is free on a stock Omarchy (SUPER + CTRL + T is Activity).
o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")

-- Optional extra bindings for the playback verbs (pick keys that are free
-- on your machine; check with `omarchy menu keybindings --print`).
-- o.bind("SUPER + SHIFT + PERIOD", "IPTV next channel", "omarchy-shell io.github.rmcdavid.iptv next")
-- o.bind("SUPER + SHIFT + COMMA", "IPTV previous channel", "omarchy-shell io.github.rmcdavid.iptv previous")

-- PAUSE LIVE TV. This is the one worth binding globally: it is the first
-- action in this plugin you want while WATCHING rather than while browsing,
-- and the guide is closed then. `c` does it inside the guide.
-- It pauses and resumes; it cannot rewind, because live streams are not
-- seekable. You can stay paused for roughly five minutes before mpv's buffer
-- fills, less on a high-bitrate channel.
-- o.bind("SUPER + SHIFT + C", "IPTV pause", "omarchy-shell io.github.rmcdavid.iptv pause")

-- Optional: picture in picture from anywhere, not just from the guide (where
-- it is `p` in list mode). Stock Omarchy already binds SUPER + O to float and
-- pin whatever window has focus, so if you only want this once in a while you
-- need nothing from us -- this is for a key that always means "the player".
-- o.bind("SUPER + SHIFT + P", "IPTV picture in picture", "omarchy-shell io.github.rmcdavid.iptv pip toggle")

-- Omarchy IPTV: add to ~/.config/hypr/bindings.lua
-- SUPER + SHIFT + T is free on a stock Omarchy (SUPER + CTRL + T is Activity).
o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")

-- Optional extra bindings for the playback verbs (pick keys that are free
-- on your machine; check with `omarchy menu keybindings --print`).
-- o.bind("SUPER + SHIFT + PERIOD", "IPTV next channel", "omarchy-shell io.github.rmcdavid.iptv next")
-- o.bind("SUPER + SHIFT + COMMA", "IPTV previous channel", "omarchy-shell io.github.rmcdavid.iptv previous")

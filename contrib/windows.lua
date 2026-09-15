-- Omarchy IPTV: optional window rules for the mpv player window.
-- Add to ~/.config/hypr/looknfeel.lua (or any file loaded by hyprland.lua).
-- The player always runs with --wayland-app-id=omarchy-iptv, so rules can
-- target that class without touching your other mpv windows.
--
-- Picture in picture does NOT need any of this. The plugin drives the window
-- at runtime with hyprctl and writes nothing to your configuration.

-- Keep video fully opaque. Omarchy tags every window `default-opacity` and
-- renders it at 0.985 / 0.96; its own exemption list for media players
-- matches on class, and ours is `omarchy-iptv`, not `mpv` -- the app id that
-- gives the plugin its window identity is the same one that costs it the
-- exemption. Confirmed on Hyprland 0.56.2, not inferred.
o.window("omarchy-iptv", { tag = "-default-opacity" })

-- Optional: always float the player at a fixed size, centered.
--
-- `size` is a two-element TABLE, not a string. Every rule in Omarchy's own
-- files spells it that way, and the installed type stub declares only
-- `enabled`, `match` and `name`, so a string here fails silently rather than
-- being reported.
--
-- Untested with picture in picture: whether a static float/size rule
-- re-applies on a surface commit -- which a playing video reaches constantly
-- -- and snaps the box back after you move it has never been measured here.
-- If you paste this line and find the PiP box jumping, drop the `size` and
-- `center` half and keep `float`.
-- o.window("omarchy-iptv", { float = true, size = { 1280, 720 }, center = true })

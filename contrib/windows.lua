-- Omarchy IPTV: optional window rules for the mpv player window.
-- Add to ~/.config/hypr/looknfeel.lua (or any file loaded by hyprland.lua).
-- The player always runs with --wayland-app-id=omarchy-iptv, so rules can
-- target that class without touching your other mpv windows.

-- Keep video fully opaque (Omarchy applies a default opacity to windows).
o.window("omarchy-iptv", { tag = "-default-opacity" })

-- Float the player at a fixed size, centered. Remove these two lines if you
-- prefer the player to tile.
-- o.window("omarchy-iptv", { float = true, size = "1280 720", center = true })

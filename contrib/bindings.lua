-- Omarchy IPTV: add to ~/.config/hypr/bindings.lua
-- SUPER + ALT + T is free on a stock Omarchy 4.0 and 4.5.0 alike.
o.bind("SUPER + ALT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")

-- Pasted an earlier copy of this file? Its first line bound SUPER + SHIFT + T,
-- which stock Omarchy binds to Activity (btop) since 4.5.0. o.bind does not
-- remove a binding already on a chord, so both are on it now. Change your
-- line to SUPER + ALT + T as above. Or, to keep T, put this line before
-- yours:
--   hl.unbind("SUPER + SHIFT + T")
-- It removes every binding on that chord, stock Activity included, so
-- Activity is then left with no key.

-- Every chord below was checked against /usr/share/omarchy/default/hypr/bindings/
-- of Omarchy 4.0.4, 4.0.6 and 4.5.0 on 2026-11-06: of SUPER + SHIFT + <letter>,
-- stock Omarchy leaves only H J K L R U V Z free on all three (4.5.0 took
-- I, Q and T). An earlier copy of this file suggested SUPER + SHIFT + C, P
-- and COMMA, which stock binds to Calendar, Google Photos and "dismiss all
-- notifications"; pasting those got you a silent fight with a webapp
-- launcher. Your own bindings.lua may differ: check with
-- `omarchy menu keybindings --print`.

-- Every command here is an `omarchy-shell <target> <method>` string, which
-- works on every Omarchy 4 release. Omarchy 4.5.0 also accepts
-- { ipc = "target.method" } in o.bind, but it splits that string at the
-- FIRST dot, and this plugin's id has dots in it:
-- { ipc = "io.github.rmcdavid.iptv.toggle" } asks a target named "io" for a
-- method named "github.rmcdavid.iptv.toggle", which nothing answers. Keep
-- the string form.

-- Optional: channel up / down from anywhere. J and K because that is what
-- they mean inside the guide (j next, k previous) and both are free.
-- o.bind("SUPER + SHIFT + J", "IPTV next channel", "omarchy-shell io.github.rmcdavid.iptv next")
-- o.bind("SUPER + SHIFT + K", "IPTV previous channel", "omarchy-shell io.github.rmcdavid.iptv previous")

-- PAUSE LIVE TV. This is the one worth binding globally: it is the first
-- action in this plugin you want while WATCHING rather than while browsing,
-- and the guide is closed then. `c` does it inside the guide.
-- It pauses and resumes. The pause lasts until mpv's forward buffer fills,
-- about four and a half minutes on a 4.7 Mbps channel, less on a higher
-- bitrate; and a long pause spends the rewind window below, one second of
-- history per paused second once the buffer is full. Z is free and sits
-- away from the H / J / K / L cluster, so a pause is never a slipped seek.
-- o.bind("SUPER + SHIFT + Z", "IPTV pause", "omarchy-shell io.github.rmcdavid.iptv pause")

-- REWIND LIVE TV. Back and forward inside the buffer mpv already keeps, and
-- back to live. The argument is the step in seconds, a positive integer;
-- leave it off for the guide's own ten. H and L because they are vim's left
-- and right, R for "return to live"; all three are free. The reply is JSON:
-- a request past what is buffered is clamped and says so, never dropped.
-- o.bind("SUPER + SHIFT + H", "IPTV back 10 s", "omarchy-shell io.github.rmcdavid.iptv back 10")
-- o.bind("SUPER + SHIFT + L", "IPTV forward 10 s", "omarchy-shell io.github.rmcdavid.iptv forward 10")
-- o.bind("SUPER + SHIFT + R", "IPTV back to live", "omarchy-shell io.github.rmcdavid.iptv live")

-- Optional: picture in picture from anywhere, not just from the guide (where
-- it is `p` in list mode). Stock Omarchy already binds SUPER + O to float and
-- pin whatever window has focus, so if you only want this once in a while you
-- need nothing from us -- this is for a key that always means "the player".
-- V for video. V is free; P is Google Photos on a stock install, and I, which
-- an earlier copy of this file suggested, switches the input language back
-- since Omarchy 4.5.0.
-- o.bind("SUPER + SHIFT + V", "IPTV picture in picture", "omarchy-shell io.github.rmcdavid.iptv pip toggle")

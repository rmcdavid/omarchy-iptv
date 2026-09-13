#EXTM3U
# QA fixture: the playlist an Xtream panel returns from get.php (docs/QA-SOURCES.md, section 8).
#  - copy the xtream/ files into the harness fixture directory; python3 -m http.server drops the query string
#    (SimpleHTTPRequestHandler.translate_path), so a request for
#        /get.php?username=user&password=pa%20ss&type=m3u_plus&output=ts
#    serves this file and the Xtream probe succeeds without any provider logic on the server side
#  - built URL for server "127.0.0.1:8765", username "user", password "pa ss":
#        http://127.0.0.1:8765/get.php?username=user&password=pa%20ss&type=m3u_plus&output=ts   -> source key 6e90a03e
#        http://127.0.0.1:8765/xmltv.php?username=user&password=pa%20ss
#  - 4 channels in 2 groups (Xtream Live, Xtream VOD); the probe result line must read "4 channels in 2 groups"
#  - the stream URLs mimic an Xtream layout (/live/<user>/<pass>/<id>.ts): "user" and "pa ss" must never
#    appear in any sink except channels.json (0600) and the edit field after Ctrl+R
#EXTINF:-1 tvg-id="qa.x.one" group-title="Xtream Live",Xtream Live One
http://127.0.0.1:9/live/user/pa%20ss/1001.ts
#EXTINF:-1 tvg-id="qa.x.two" group-title="Xtream Live",Xtream Live Two
http://127.0.0.1:9/live/user/pa%20ss/1002.ts
#EXTINF:-1 tvg-id="qa.x.three" group-title="Xtream Live",Xtream Live Three
http://127.0.0.1:9/live/user/pa%20ss/1003.ts
#EXTINF:-1 tvg-id="qa.x.vod" group-title="Xtream VOD",Xtream Movie
http://127.0.0.1:9/movie/user/pa%20ss/2001.mp4

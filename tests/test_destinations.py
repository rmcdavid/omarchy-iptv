"""D-SINK-40, D-SINK-41, D-SINK-42 (2026-10-29): where provider data may send
this machine.

The owner's policy: a source the USER typed may reach any address on its
first hop; a destination the PROVIDER chose -- a guide hint, a redirect hop,
a logo, a channel URL, a nested entry -- may not reach a non-global address
unless it is the user's own playlist host, in the same class. udp and rtp
only to multicast groups; no stream form that listens; no sign-in header to
another host.

How this module observes it, and why:

* The shared fixture tests/fixtures/destinations.json is run here against
  the helper and in tests/Model.test.js against the model (one rule, two
  languages, one file).
* The connect-time policy is observed by running the SHIPPING helper as a
  subprocess, the way the service runs it, against logging servers on
  127.0.0.1 and 127.0.0.2 (both loopback; nothing leaves the machine), with
  the URL and its provenance in the environment as the service sets them.
  "Refused" means the refused server logged nothing at all, not that the
  helper said so.
* A PUBLIC first hop cannot be made on this machine, so the cases that need
  one run in process under the one seam, helper_loader.loopback_reads_public,
  which calls 127.0.0.1 global and nothing else; LoopbackSeamTest holds the
  seam to exactly that.
"""
import contextlib
import http.server
import io
import ipaddress
import json
import os
import pathlib
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper, loopback_reads_public
from scripted_server import ScriptedServer, response

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "destinations.json").read_text(encoding="ascii"))
PLAYLIST = b"#EXTM3U\n#EXTINF:-1 tvg-id=\"a.test\",A\nhttp://stream.example.test/a.m3u8\n"
XMLTV = (b'<?xml version="1.0"?><tv><channel id="a.test"><display-name>A</display-name></channel>'
         b'<programme start="20260101000000 +0000" stop="20991231000000 +0000" channel="a.test"><title>T</title></programme></tv>')


class LoggingServer:
    """HTTP on `host` (127.0.0.1 or 127.0.0.2). `routes` maps a path -- or,
    for a proxy, the absolute URL a proxy is asked for -- to (status,
    headers, body). `seen` is every request line's target with its
    Authorization header, in order."""

    def __init__(self, routes, host="127.0.0.1"):
        seen = self.seen = []
        table = self.routes = dict(routes)

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization")))
                status, headers, body = table.get(self.path, (404, (), b""))
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

        self.httpd = http.server.ThreadingHTTPServer((host, 0), Handler)
        self.httpd.daemon_threads = True
        self.host = host
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path, host=None):
        return "http://%s:%d%s" % (host or self.host, self.port, path)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class Listener:
    """A TCP listener that only COUNTS the connections it accepts: what a
    refused destination must never see."""

    def __init__(self, host="127.0.0.2"):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((host, 0))
        self.sock.listen(8)
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.accepted = 0
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.accepted += 1
            conn.close()

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=5)
        self.sock.close()


def run_helper(argv, env):
    """The shipping helper as a subprocess, the service's way: the URL and
    its provenance in the environment, nothing of the test's own proxy
    settings inherited unless the case sets them. -> (exit, last JSON line)."""
    merged = {k: v for k, v in os.environ.items()
              if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
              and not k.startswith("OMARCHY_IPTV_")}
    merged.update(env)
    done = subprocess.run([sys.executable, str(HELPER), *argv], capture_output=True, text=True,
                          env=merged, timeout=60)
    lines = [l for l in done.stdout.strip().splitlines() if l.strip()]
    return done.returncode, (json.loads(lines[-1]) if lines else None), done.stderr


class FixtureTest(unittest.TestCase):
    """The shared fixture, helper side."""

    def test_every_host_spelling_classifies_and_keys_as_the_fixture_says(self):
        got = [(r["host"], helper.host_class(r["host"]), helper.host_key(r["host"])) for r in FIXTURE["hosts"]]
        self.assertEqual(got, [(r["host"], r["class"], r["key"]) for r in FIXTURE["hosts"]])

    def test_the_table_is_never_more_forgiving_than_ipaddress(self):
        """Every address the explicit table calls global, CPython's is_global
        calls global too -- over the fixture's literals and over both edges of
        every network in the table and the address either side of each."""
        literals = [helper.parse_ip_literal(r["host"]) for r in FIXTURE["hosts"]]
        probes = [a for a in literals if a is not None]
        for text, _ in helper._ADDRESS_TABLE_V4 + helper._ADDRESS_TABLE_V6:
            net = ipaddress.ip_network(text)
            top = 2 ** (32 if net.version == 4 else 128) - 1
            for value in (int(net.network_address) - 1, int(net.network_address),
                          int(net.broadcast_address), int(net.broadcast_address) + 1):
                if 0 <= value <= top:
                    probes.append(ipaddress.ip_address(value) if net.version == 4 else ipaddress.IPv6Address(value))
        looser = [str(a) for a in probes if helper.address_class(a) == "global" and not a.is_global]
        self.assertEqual(looser, [])
        self.assertGreater(len(probes), 150)

    def test_the_stream_gate_reads_every_form_as_the_fixture_says(self):
        got = [(r["url"], helper.stream_listen_refusal(r["url"]), helper.is_stream_url(r["url"])) for r in FIXTURE["streams"]]
        self.assertEqual(got, [(r["url"], r["listen"], r["stream"]) for r in FIXTURE["streams"]])

    def test_the_channel_host_rule_reads_every_row_as_the_fixture_says(self):
        got = [(r["url"], r["source"], helper.stream_host_refused(r["url"], r["source"])) for r in FIXTURE["streamHosts"]]
        self.assertEqual(got, [(r["url"], r["source"], r["refused"]) for r in FIXTURE["streamHosts"]])

    def test_the_parse_reads_every_host_row_as_play_time_does(self):
        """rc-p1b (2026-10-29): parse_m3u's one read (stream_entry_refusal)
        and the play-time rule (stream_host_refused, which player_target runs
        again) are two readings of ONE rule, and the parse took the scheme's
        default port for a port that does not PARSE -- `127.0.0.1:631:80` was
        the port-80 home to it and refused at play time, a channel listed
        that can never play. Every row: the parse refuses on the host rule
        exactly when play time refuses -- `local`, or since D-SINK-57's scope
        (lane-p1c, 2026-10-29) `port` for a loopback relay's channel on
        another port of this machine, which a row's `reason` names."""
        got = [(r["url"], helper.stream_entry_refusal(r["url"], r["source"])[0] in ("local", "port"))
               for r in FIXTURE["streamHosts"]]
        self.assertEqual(got, [(r["url"], r["refused"]) for r in FIXTURE["streamHosts"]])
        self.assertIn("http://127.0.0.1:631:80/x", [r["url"] for r in FIXTURE["streamHosts"]])
        named = [(r["url"], helper.stream_entry_refusal(r["url"], r["source"])[0]) for r in FIXTURE["streamHosts"] if "reason" in r]
        self.assertEqual(named, [(r["url"], r["reason"]) for r in FIXTURE["streamHosts"] if "reason" in r])
        self.assertIn("port", [r.get("reason") for r in FIXTURE["streamHosts"]])

    def test_the_own_host_rule_counts_the_port_on_loopback_only(self):
        """D-SINK-57 (owner, 2026-10-29), the shared rows: on loopback the
        playlist's own host is host AND port; a LAN or public host keeps any
        port; a port nobody knows matches nothing."""
        got = [(r["name"], helper.own_host_match(r["host"], r["port"], r["home"])) for r in FIXTURE["ownHosts"]]
        self.assertEqual(got, [(r["name"], r["same"]) for r in FIXTURE["ownHosts"]])
        self.assertGreaterEqual(len(got), 15)

    def test_a_url_port_is_the_named_one_or_the_schemes_default(self):
        got = [(r["url"], helper.url_port(r["url"])) for r in FIXTURE["urlPorts"]]
        self.assertEqual(got, [(r["url"], r["port"]) for r in FIXTURE["urlPorts"]])

    def test_the_names_the_shell_and_the_helper_share(self):
        self.assertEqual(FIXTURE["env"], {"url": helper.URL_ENV, "origin": helper.ORIGIN_ENV,
                                          "playlistHost": helper.HOME_HOST_ENV, "playlistClass": helper.HOME_CLASS_ENV,
                                          "playlistPort": helper.HOME_PORT_ENV})
        self.assertEqual((FIXTURE["classes"], FIXTURE["destinationRules"]),
                         (list(helper.ADDRESS_CLASSES), helper.DESTINATION_RULES))


class ConnectPolicyTest(unittest.TestCase):
    """The shipping helper, as a subprocess, against 127.0.0.1 / 127.0.0.2."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def serve(self, routes, host="127.0.0.1"):
        server = LoggingServer(routes, host)
        self.addCleanup(server.close)
        return server

    def playlist(self, url, **env):
        env.update({helper.URL_ENV: url})
        return run_helper(["playlist", "--cache-dir", self.cache, "--timeout", "5"], env)

    def epg(self, url, **env):
        env.update({helper.URL_ENV: url})
        return run_helper(["epg", "--cache-dir", self.cache, "--timeout", "5"], env)

    def test_a_same_host_redirect_from_a_typed_loopback_source_is_followed(self):
        """Same host AND, on loopback, the same port (D-SINK-57): a relay
        redirecting within itself is followed."""
        a = self.serve({"/pl.m3u": (200, (), PLAYLIST)})
        a.routes["/start.m3u"] = (302, (("Location", a.url("/pl.m3u")),), b"")
        code, status, err = self.playlist(a.url("/start.m3u"), OMARCHY_IPTV_ORIGIN="user")
        self.assertEqual((code, status["ok"], status["channelCount"]), (0, True, 1), err)
        self.assertEqual(a.seen, [("/start.m3u", None), ("/pl.m3u", None)])
        cached = json.loads((pathlib.Path(self.cache) / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual((cached["sourceClass"], status["destinationRules"]), ("loopback", helper.DESTINATION_RULES))
        # D-SINK-57/58: and what play time needs to run the parse's rules again.
        self.assertEqual((cached["sourcePort"], cached["sourceLocal"]), (a.port, True))

    def test_a_redirect_to_another_port_on_loopback_is_refused_and_never_contacted(self):
        """D-SINK-57 (owner, 2026-10-29), the review's reproduction 1: a typed
        loopback source whose 302 names the same host on ANOTHER port. Until
        this the same-host exception ignored ports, so anything on loopback --
        the print server, a local API -- was the relay's own host."""
        b = self.serve({"/admin": (200, (), PLAYLIST)})
        a = self.serve({"/start.m3u": (302, (("Location", b.url("/admin?op=x")),), b"")})
        code, status, err = self.playlist(a.url("/start.m3u"), OMARCHY_IPTV_ORIGIN="user")
        self.assertEqual((code, status["error"]["code"]), (1, "local_address"), err)
        self.assertEqual(b.seen, [], "the other port received a request")
        self.assertNotIn("op=x", json.dumps(status) + err)

    def test_a_redirect_to_another_loopback_host_is_refused_and_never_contacted(self):
        b = self.serve({"/cgi-bin/admin": (200, (), PLAYLIST)}, host="127.0.0.2")
        a = self.serve({"/start.m3u": (302, (("Location", b.url("/cgi-bin/admin?action=reboot")),), b"")})
        code, status, err = self.playlist(a.url("/start.m3u"), OMARCHY_IPTV_ORIGIN="user")
        self.assertEqual((code, status["error"]["code"]), (1, "local_address"), err)
        self.assertEqual(b.seen, [], "the refused host received a request")
        self.assertEqual(status["error"]["message"], FIXTURE["refusals"][0]["reply"]["error"]["message"])
        self.assertEqual(status["sourceHost"], FIXTURE["refusals"][0]["reply"]["sourceHost"])
        self.assertNotIn("reboot", status["error"]["message"] + err)

    def test_a_redirect_to_localhost_is_another_host_and_is_refused(self):
        b = self.serve({"/x.m3u": (200, (), PLAYLIST)})
        a = self.serve({"/start.m3u": (302, (("Location", b.url("/x.m3u", host="localhost")),), b"")})
        code, status, err = self.playlist(a.url("/start.m3u"), OMARCHY_IPTV_ORIGIN="user")
        self.assertEqual((code, status["error"]["code"]), (1, "local_address"), err)
        self.assertEqual(b.seen, [])

    def test_a_typed_url_with_no_provenance_is_the_users(self):
        """A human at their own shell: no ORIGIN, `--url` or the variable."""
        a = self.serve({"/pl.m3u": (200, (), PLAYLIST)})
        code, status, err = run_helper(["playlist", "--url", a.url("/pl.m3u"), "--cache-dir", self.cache], {})
        self.assertEqual((code, status["ok"]), (0, True), err)

    def test_a_hinted_guide_on_a_loopback_host_is_refused_and_never_contacted(self):
        a = self.serve({"/epg-lan": (200, (), XMLTV)})
        code, status, err = self.epg(a.url("/epg-lan?from=hint"), OMARCHY_IPTV_ORIGIN="playlist")
        self.assertEqual((code, status["error"]["code"]), (1, "local_address"), err)
        self.assertEqual(a.seen, [])
        self.assertEqual(status["error"]["message"], FIXTURE["refusals"][1]["reply"]["error"]["message"])

    def test_an_origin_the_helper_does_not_know_reads_as_the_providers(self):
        a = self.serve({"/epg-lan": (200, (), XMLTV)})
        for origin in ("admin", "USER", " playlist", "1"):
            with self.subTest(origin=origin):
                code, status, err = self.epg(a.url("/epg-lan"), OMARCHY_IPTV_ORIGIN=origin)
                self.assertEqual(status["error"]["code"], "local_address", err)
        self.assertEqual(a.seen, [])

    def test_a_hinted_guide_on_the_playlists_own_host_and_class_is_fetched(self):
        a = self.serve({"/xmltv": (200, (), XMLTV)})
        code, status, err = self.epg(a.url("/xmltv"), OMARCHY_IPTV_ORIGIN="playlist",
                                     OMARCHY_IPTV_PLAYLIST_HOST="127.0.0.1", OMARCHY_IPTV_PLAYLIST_CLASS="loopback",
                                     OMARCHY_IPTV_PLAYLIST_PORT=str(a.port))
        self.assertEqual((code, status["ok"]), (0, True), err)
        self.assertEqual(a.seen, [("/xmltv", None)])

    def test_a_hinted_guide_on_another_port_of_a_loopback_playlist_host_is_refused(self):
        """D-SINK-57: the playlist's own LOOPBACK host is its port too, so a
        hint naming the same address on another port -- or with the shell
        saying no port at all -- is refused and never contacted."""
        a = self.serve({"/xmltv": (200, (), XMLTV)})
        for port in (str(a.port + 1 if a.port < 65535 else a.port - 1), "", "0", "65536", "80x"):
            with self.subTest(port=port):
                code, status, err = self.epg(a.url("/xmltv"), OMARCHY_IPTV_ORIGIN="playlist",
                                             OMARCHY_IPTV_PLAYLIST_HOST="127.0.0.1",
                                             OMARCHY_IPTV_PLAYLIST_CLASS="loopback", OMARCHY_IPTV_PLAYLIST_PORT=port)
                self.assertEqual((code, status["error"]["code"]), (1, "local_address"), err)
        self.assertEqual(a.seen, [])

    def test_the_same_host_in_another_class_than_its_playlist_fetch_is_refused(self):
        """The DNS-rebinding shape: the playlist's own name answered a public
        address when the playlist was fetched and answers loopback now."""
        a = self.serve({"/xmltv": (200, (), XMLTV)})
        code, status, err = self.epg(a.url("/xmltv"), OMARCHY_IPTV_ORIGIN="playlist",
                                     OMARCHY_IPTV_PLAYLIST_HOST="127.0.0.1", OMARCHY_IPTV_PLAYLIST_CLASS="global")
        self.assertEqual(status["error"]["code"], "local_address", err)
        self.assertEqual(a.seen, [])

    def test_a_hint_carrying_userinfo_sends_no_credential(self):
        a = self.serve({"/apply.cgi": (200, (), XMLTV)})
        url = a.url("/apply.cgi?reboot=1").replace("http://", "http://admin:admin@")
        code, status, err = self.epg(url, OMARCHY_IPTV_ORIGIN="playlist",
                                     OMARCHY_IPTV_PLAYLIST_HOST="127.0.0.1", OMARCHY_IPTV_PLAYLIST_CLASS="loopback")
        self.assertEqual((code, status["error"]["code"]), (1, "bad_url"), err)
        self.assertEqual(a.seen, [])
        self.assertNotIn("admin:admin", json.dumps(status) + err)

    def test_a_typed_guide_with_userinfo_still_sends_it(self):
        a = self.serve({"/xmltv": (200, (), XMLTV)})
        url = a.url("/xmltv").replace("http://", "http://me:pw@")
        code, status, err = self.epg(url, OMARCHY_IPTV_ORIGIN="user")
        self.assertEqual((code, status["ok"]), (0, True), err)
        self.assertEqual(a.seen, [("/xmltv", "Basic bWU6cHc=")])

    def test_a_local_list_keeps_its_local_streams_and_drops_a_sign_in_header_for_another_host(self):
        a = self.serve({})
        body = (b"#EXTM3U\n#EXTINF:-1,Tuner\n"
                b"#KODIPROP:inputstream.adaptive.stream_headers=Cookie=a%3Db&X-Ok=1\n"
                b"http://192.168.1.20:5004/auto/v1\n"
                b"#EXTINF:-1,Own\n#KODIPROP:inputstream.adaptive.stream_headers=Authorization=Basic%20eA%3D%3D\n"
                + a.url("/stream/1").encode() + b"\n"
                # D-SINK-57's scope (the lead, 2026-10-29): the same loopback
                # address on ANOTHER port is another service of this machine,
                # which a relay's playlist does not name: the channel is
                # skipped and counted, not merely stripped of its header.
                b"#EXTINF:-1,Cups\n#KODIPROP:inputstream.adaptive.stream_headers=Authorization=Basic%20eQ%3D%3D\n"
                b"http://127.0.0.1:631/admin\n"
                b"#EXTINF:-1,Localhost\nhttp://localhost:1/x\n"
                b"#EXTINF:-1,Listener\nsrt://0.0.0.0:9000?mode=listener\n")
        a.routes["/pl.m3u"] = (200, (), body)
        code, status, err = self.playlist(a.url("/pl.m3u"), OMARCHY_IPTV_ORIGIN="user")
        self.assertEqual((code, status["channelCount"]), (0, 2), err)
        channels = json.loads((pathlib.Path(self.cache) / "channels.json").read_text(encoding="utf-8"))["channels"]
        self.assertEqual([(c["name"], c.get("headers")) for c in channels],
                         [("Tuner", {"X-Ok": "1"}), ("Own", {"Authorization": "Basic eA=="})])
        self.assertIn("1 sign-in header dropped: its channel is on another host than the playlist", status["warnings"])
        self.assertIn("2 entries skipped: stream addresses on this machine at other ports than the playlist's",
                      status["warnings"])
        self.assertIn("1 entry skipped: the stream would listen on this machine for anyone to send to", status["warnings"])


class LoopbackSeamTest(unittest.TestCase):
    """The seam is exactly one address wide, and the real classifier refuses
    what it lets through."""

    def test_the_seam_widens_one_address_and_nothing_wrapped_or_next_to_it(self):
        with loopback_reads_public(helper):
            under = [helper.address_class(a) for a in ("127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1", "64:ff9b::7f00:1")]
        self.assertEqual(under, ["global", "loopback", "loopback", "loopback", "loopback"])
        self.assertEqual(helper.address_class("127.0.0.1"), "loopback")


class PublicFirstHopTest(unittest.TestCase):
    """In process, under the seam: 127.0.0.1 plays the public provider."""

    def setUp(self):
        seam = loopback_reads_public(helper)
        seam.start()
        self.addCleanup(seam.stop)
        # The whole environment is put back when the patch stops, so the
        # proxy variables removed inside it come back with it.
        patcher = mock.patch.dict(os.environ, {helper.ORIGIN_ENV: "user"})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
            os.environ.pop(name, None)

    def serve(self, routes, host="127.0.0.1"):
        server = LoggingServer(routes, host)
        self.addCleanup(server.close)
        return server

    def test_a_public_provider_that_redirects_into_loopback_is_refused(self):
        lan = self.serve({"/cgi-bin/luci": (200, (), PLAYLIST)}, host="127.0.0.2")
        provider = self.serve({"/pl.m3u": (302, (("Location", lan.url("/cgi-bin/luci")),), b"")})
        policy = helper.DestinationPolicy.from_environment("playlist")
        with self.assertRaises(helper.HelperError) as caught:
            helper.read_http_source(provider.url("/pl.m3u"), 5, "playlist", policy)
        self.assertEqual(caught.exception.code, "local_address")
        self.assertEqual(lan.seen, [])
        self.assertEqual((policy.first_class, policy.hops), ("global", 2))

    def test_a_public_provider_that_redirects_to_its_own_host_is_followed(self):
        provider = self.serve({"/pl.m3u": (302, (("Location", "/real.m3u"),), b""), "/real.m3u": (200, (), PLAYLIST)})
        policy = helper.DestinationPolicy.from_environment("playlist")
        self.assertEqual(helper.read_http_source(provider.url("/pl.m3u"), 5, "playlist", policy), PLAYLIST)
        self.assertEqual((policy.first_class, policy.last_class), ("global", "global"))

    def test_a_public_list_loses_its_lan_streams_and_says_so(self):
        body = (b"#EXTM3U\n#EXTINF:-1,Router\n#KODIPROP:inputstream.adaptive.stream_headers=Authorization=Basic%20YWRtaW46YWRtaW4%3D\n"
                b"http://192.168.1.1/cgi-bin/reboot.cgi\n#EXTINF:-1,Printer\nhttp://127.0.0.2:631/admin\n"
                b"#EXTINF:-1,Fine\nhttp://stream.example.test/a.m3u8\n")
        provider = self.serve({"/pl.m3u": (200, (), body)})
        with tempfile.TemporaryDirectory() as cache:
            out = io.StringIO()
            with mock.patch.dict(os.environ, {helper.URL_ENV: provider.url("/pl.m3u")}), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(helper.main(["playlist", "--cache-dir", cache]), 0)
            status = json.loads(out.getvalue().strip().splitlines()[-1])
            cached = json.loads((pathlib.Path(cache) / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual([c["name"] for c in cached["channels"]], ["Fine"])
        self.assertEqual(cached["sourceClass"], "global")
        self.assertIn("2 entries skipped: stream addresses on this machine or a local network, from a playlist that is not",
                      status["warnings"])

    def test_the_policy_itself(self):
        """The decisions, called: first hop of a typed URL; same host, same
        class; the playlist's host in its recorded class; nothing else."""
        user = helper.DestinationPolicy("playlist", "user")
        self.assertTrue(user.permits("tvh.lan", "private", True))
        user.connected("tvh.lan", "private", True)
        self.assertEqual([user.permits("TVH.LAN.", "private", False), user.permits("tvh.lan", "loopback", False),
                          user.permits("nas.lan", "private", False), user.permits("cdn.test", "global", False)],
                         [True, False, False, True])
        public = helper.DestinationPolicy("playlist", "user")
        public.connected("p.example.test", "global", True)
        self.assertFalse(public.permits("p.example.test", "private", False))
        hint = helper.DestinationPolicy("EPG", "playlist", "tvh.lan", "private")
        self.assertEqual([hint.permits("tvh.lan", "private", True), hint.permits("tvh.lan", "loopback", True),
                          hint.permits("other.lan", "private", True)], [True, False, False])
        named = helper.DestinationPolicy("EPG", "playlist", "tvh.lan", "")
        self.assertFalse(named.permits("tvh.lan", "private", True), "a name with no recorded class must fail closed")
        literal = helper.DestinationPolicy("EPG", "playlist", "192.168.1.5", "")
        self.assertTrue(literal.permits("192.168.1.5", "private", True), "a literal's class needs no record")
        logos = helper.DestinationPolicy.for_logos()
        self.assertEqual([logos.permits("cdn.test", "global", True), logos.permits("127.0.0.1", "loopback", True)], [True, False])
        # The logo flag outranks every provenance: even a logo policy built
        # as if the user had typed its host, on the playlist's own host, in
        # its own class, reaches nothing but a global address.
        typed = helper.DestinationPolicy("logo", "user", "cdn.lan", "private", logos=True)
        typed.connected("cdn.lan", "private", True)
        self.assertEqual([typed.permits("cdn.lan", "private", True), typed.permits("cdn.lan", "private", False),
                          typed.permits("cdn.lan", "global", False)], [False, False, True])


def unshare_works():
    if not (shutil.which("unshare") and shutil.which("ip")):
        return False
    try:
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(unshare_works(), "needs `unshare -rn` (an unprivileged network namespace) and `ip`")
class PublicProviderInANamespaceTest(unittest.TestCase):
    """No seam at all: tests/netns_public.py, inside `unshare -rn`, gives a
    dummy interface the address 11.0.0.1 -- global to the REAL classifier,
    and reachable only inside that namespace -- and runs the shipping
    helper as a subprocess against a provider there and a LAN host on
    127.0.0.1."""

    def test_a_public_provider_cannot_redirect_into_this_machine_and_its_lan_streams_are_skipped(self):
        with tempfile.TemporaryDirectory() as scratch:
            env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS")}
            done = subprocess.run(["unshare", "-rn", sys.executable, "-I", str(ROOT / "tests" / "netns_public.py"),
                                   str(HELPER), scratch], capture_output=True, text=True, env=env, timeout=120)
        result = json.loads(done.stdout.strip().splitlines()[-1])
        if "skip" in result:
            self.skipTest(result["skip"])
        self.assertEqual(result["redirect"]["code"], "local_address", done.stderr)
        self.assertEqual([s for s in result["redirect"]["seen"] if s.startswith("127.")], [], "this machine was contacted")
        self.assertEqual((result["same"]["ok"], result["same"]["sourceClass"], result["same"]["names"]), (True, "global", ["Fine"]))
        self.assertIn("1 entry skipped: a stream address on this machine or a local network, from a playlist that is not",
                      result["same"]["warnings"])


class LogoDestinationTest(unittest.TestCase):
    """A logo never reaches this machine or a local network, on any hop."""

    def test_a_logo_on_loopback_is_refused_before_any_connection(self):
        target = Listener("127.0.0.1")
        self.addCleanup(target.close)
        with self.assertRaises(helper.HelperError) as caught:
            helper.fetch_logo("https://127.0.0.1:%d/logo.png" % target.port, 5)
        self.assertEqual((caught.exception.code, target.accepted), ("local_address", 0))

    @unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a certificate")
    def test_a_logo_redirect_into_loopback_is_refused_before_any_connection(self):
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        key, cert = os.path.join(work, "k.pem"), os.path.join(work, "c.pem")
        made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                               "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                               "-keyout", key, "-out", cert], capture_output=True, timeout=60)
        if made.returncode != 0:
            self.skipTest("openssl could not make a certificate")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        # The seam makes 127.0.0.1 the public logo host; the redirect aims at
        # another loopback address. (localhost would resolve to the seam's
        # own 127.0.0.1 here; ConnectPolicyTest refuses it without the seam.)
        target = Listener("127.0.0.2")
        self.addCleanup(target.close)
        where = "https://127.0.0.2:%d/logo.png" % target.port
        server = ScriptedServer({"/logo.png": (response("302 Found", (("Location", where),)),)}, context)
        self.addCleanup(server.close)
        with loopback_reads_public(helper), mock.patch.dict(os.environ, {"SSL_CERT_FILE": cert}):
            with self.assertRaises(helper.HelperError) as caught:
                helper.fetch_logo(server.url("/logo.png"), 5)
        self.assertEqual((caught.exception.code, target.accepted, server.paths), ("local_address", 0, ["/logo.png"]))


class ProxyTest(unittest.TestCase):
    """Through a proxy the socket goes to the proxy (the user's choice); the
    TARGET is what is checked, by name, before the proxy is asked."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def test_a_typed_url_through_a_proxy_works_and_a_redirect_into_loopback_through_it_is_refused(self):
        target = "http://192.0.2.10/pl.m3u"
        proxy = LoggingServer({target: (302, (("Location", "http://127.0.0.2:9/admin"),), b"")})
        self.addCleanup(proxy.close)
        code, status, err = run_helper(["playlist", "--cache-dir", self.cache, "--timeout", "5"],
                                       {helper.URL_ENV: target, helper.ORIGIN_ENV: "user",
                                        "http_proxy": "http://127.0.0.1:%d" % proxy.port})
        self.assertEqual((code, status["error"]["code"]), (1, "local_address"), err)
        self.assertEqual(proxy.seen, [(target, None)], "only the typed first hop went to the proxy")

    def test_a_hint_into_loopback_is_refused_without_asking_the_proxy(self):
        proxy = LoggingServer({})
        self.addCleanup(proxy.close)
        code, status, err = run_helper(["epg", "--cache-dir", self.cache, "--timeout", "5"],
                                       {helper.URL_ENV: "http://127.0.0.2:9/epg.xml", helper.ORIGIN_ENV: "playlist",
                                        "http_proxy": "http://127.0.0.1:%d" % proxy.port})
        self.assertEqual(status["error"]["code"], "local_address", err)
        self.assertEqual(proxy.seen, [])

    def test_a_provider_chosen_target_this_machine_cannot_resolve_is_refused_without_asking_the_proxy(self):
        """Behind a proxy with no local DNS: the target is unknowable here, so
        a hop the provider chose is refused (in process: the lookup is made
        to fail for that one name, which is LESS forgiving than any resolver,
        and nothing leaves the machine)."""
        proxy = LoggingServer({})
        self.addCleanup(proxy.close)
        real = helper.resolve_within

        def lookup(host, port, timeout):
            if host == "guide.example.test":
                raise socket.gaierror(-2, "Name or service not known")
            return real(host, port, timeout)
        with mock.patch.object(helper, "resolve_within", lookup), \
                mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:%d" % proxy.port, helper.ORIGIN_ENV: "playlist"}):
            os.environ.pop("no_proxy", None)
            os.environ.pop("NO_PROXY", None)
            with self.assertRaises(helper.HelperError) as caught:
                helper.read_http_source("http://guide.example.test/epg.xml", 5, "EPG")
        self.assertEqual(caught.exception.code, "network")
        self.assertIn("could not resolve guide.example.test", caught.exception.message)
        self.assertEqual(proxy.seen, [])

    def test_every_address_a_proxied_target_answers_must_be_allowed(self):
        """check_proxied, called (the recheck of lane-dest: a mutant that
        checked ONE address of the answer survived the suite). The proxy may
        connect to any address the name answers, so a single non-global one
        among global ones is a refusal, in either order; the lookup is made to
        answer two addresses for that one name, which any resolver can."""
        for answer in (("8.8.8.8", "127.0.0.1"), ("127.0.0.1", "8.8.8.8"), ("8.8.4.4", "10.0.0.5")):
            def lookup(host, port, timeout, answer=answer):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in answer]
            policy = helper.DestinationPolicy("playlist", "user")
            policy.connected("p.example.test", "global", True)
            with mock.patch.object(helper, "resolve_within", lookup):
                with self.assertRaises(helper.HelperError) as caught:
                    policy.check_proxied("cdn.example.test", 80, 5, False)
            self.assertEqual(caught.exception.code, "local_address", answer)

        def single(host, port, timeout):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]
        policy = helper.DestinationPolicy("playlist", "user")
        policy.connected("p.example.test", "global", True)
        with mock.patch.object(helper, "resolve_within", single):
            policy.check_proxied("cdn.example.test", 80, 5, False)
        self.assertEqual(policy.last_class, "global")

    def test_a_typed_first_hop_this_machine_cannot_resolve_is_no_local_source(self):
        """The lane's decision, pinned: behind a proxy with no local DNS the
        typed first hop is allowed as `unresolved`, and a source of that class
        is NOT local, so its list's LAN literals are still skipped (a mutant
        that read `unresolved` as local survived the suite)."""
        def lookup(host, port, timeout):
            raise socket.gaierror(-2, "Name or service not known")
        policy = helper.DestinationPolicy("playlist", "user")
        with mock.patch.object(helper, "resolve_within", lookup):
            policy.check_proxied("tvh.example.test", 80, 5, policy.begin_hop())
        self.assertEqual((policy.first_class, policy.last_class), ("unresolved", "unresolved"))
        source = helper.playlist_source("http", "http://tvh.example.test/pl.m3u", policy.last_class)
        self.assertFalse(source["local"])
        parsed = helper.parse_m3u(["#EXTM3U", "#EXTINF:-1,L", "http://10.0.0.5/x", "#EXTINF:-1,P", "http://cdn.example.test/x"], source)
        self.assertEqual([c["name"] for c in parsed["channels"]], ["P"])

    def test_a_typed_first_hop_through_the_proxy_is_fetched(self):
        target = "http://192.0.2.10/pl.m3u"
        proxy = LoggingServer({target: (200, (), PLAYLIST)})
        self.addCleanup(proxy.close)
        code, status, err = run_helper(["playlist", "--cache-dir", self.cache, "--timeout", "5"],
                                       {helper.URL_ENV: target, helper.ORIGIN_ENV: "user",
                                        "http_proxy": "http://127.0.0.1:%d" % proxy.port})
        self.assertEqual((code, status["ok"]), (0, True), err)


class StreamGateTest(unittest.TestCase):
    """parse time and play time."""

    def test_a_parse_without_a_source_fails_closed(self):
        result = helper.parse_m3u("#EXTM3U\n#EXTINF:-1,R\n#KODIPROP:inputstream.adaptive.stream_headers=Cookie=a%3Db\n"
                                  "http://stream.example.test/x\n#EXTINF:-1,L\nhttp://10.0.0.5/x\n")
        self.assertEqual([(c["name"], c.get("headers")) for c in result["channels"]], [("R", None)])
        self.assertEqual(result["warnings"], [
            "1 entry skipped: a stream address on this machine or a local network, from a playlist that is not",
            "1 sign-in header dropped: its channel is on another host than the playlist"])

    def test_every_sign_in_header_is_kept_only_on_the_playlists_own_host(self):
        text = ("#EXTM3U\n#EXTINF:-1,Own\n#KODIPROP:inputstream.adaptive.stream_headers=Authorization=a&Cookie=b&Proxy-Authorization=c&Host=d&X-Ok=1\n"
                "http://P.Example.TEST:8080/live/1\n#EXTINF:-1,Cdn\n#KODIPROP:inputstream.adaptive.stream_headers=authorization=a&cookie=b&X-Ok=1\n"
                "http://cdn.example.test/live/2\n")
        result = helper.parse_m3u(text, {"host": "p.example.test", "local": False})
        self.assertEqual([c.get("headers") for c in result["channels"]],
                         [{"Authorization": "a", "Cookie": "b", "Proxy-Authorization": "c", "Host": "d", "X-Ok": "1"}, {"X-Ok": "1"}])
        self.assertIn("2 sign-in headers dropped: their channels are on other hosts than the playlist", result["warnings"])

    def test_host_and_proxy_authorization_are_sign_in_headers_too(self):
        """The two of the four the suite never put on another host's channel
        (a mutant that forgot `host` survived it): a forged Host, and a
        proxy credential, for a channel off the playlist's own host."""
        text = ("#EXTM3U\n#EXTINF:-1,Cdn\n#KODIPROP:inputstream.adaptive.stream_headers="
                "HOST=p.example.test&proxy-authorization=c&X-Ok=1\nhttp://cdn.example.test/live/2\n")
        result = helper.parse_m3u(text, {"host": "p.example.test", "local": False})
        self.assertEqual([c.get("headers") for c in result["channels"]], [{"X-Ok": "1"}])
        self.assertIn("2 sign-in headers dropped: their channels are on other hosts than the playlist", result["warnings"])

    def test_a_typed_name_that_connected_to_loopback_holds_the_port_rule(self):
        """D-SINK-57: "a name whose playlist fetch connected to loopback" is a
        loopback home too, not only a literal or a localhost name -- read from
        the first hop's class (playlist_source's `first_class`). A mutant
        that read loopback from the literal alone survived the suite (rc-p1b):
        the relay's own port keeps its sign-in headers, another port of the
        same name does not."""
        source = helper.playlist_source("http", "http://relay.example.test:34400/m3u", "loopback", "loopback")
        self.assertEqual((source["host"], source["port"], source["loopback"], source["local"]),
                         ("relay.example.test", 34400, True, True))
        text = ("#EXTM3U\n#EXTINF:-1,Own\n#KODIPROP:inputstream.adaptive.stream_headers=Cookie=a&X-Ok=1\n"
                "http://relay.example.test:34400/s/1\n#EXTINF:-1,Other\n"
                "#KODIPROP:inputstream.adaptive.stream_headers=Cookie=a&X-Ok=1\nhttp://relay.example.test:631/s/2\n")
        result = helper.parse_m3u(text, source)
        self.assertEqual([c.get("headers") for c in result["channels"]], [{"Cookie": "a", "X-Ok": "1"}, {"X-Ok": "1"}])

    def test_a_cached_listening_url_is_refused_at_play_time(self):
        """A cache written before the rule: player_target re-checks it."""
        with tempfile.TemporaryDirectory() as cache:
            (pathlib.Path(cache) / "channels.json").write_text(json.dumps({"version": 1, "channels": [
                {"id": "u", "name": "U", "group": "G", "url": "udp://0.0.0.0:53317"},
                {"id": "s", "name": "S", "group": "G", "url": "srt://0.0.0.0:9000?mode=listener"},
                {"id": "m", "name": "M", "group": "G", "url": "udp://@239.1.1.1:1234"}]}), encoding="utf-8")
            refused = []
            for cid in ("u", "s"):
                with self.assertRaises(helper.HelperError) as caught:
                    helper.player_target(cid, "", cache)
                refused.append(caught.exception.code)
            self.assertEqual(refused, ["unsupported_scheme", "unsupported_scheme"])
            self.assertEqual(helper.player_target("m", "", cache)["url"], "udp://@239.1.1.1:1234")

    # The recheck of lane-dest (2026-10-29). The helper reads a channel URL's
    # host with urlsplit; the player reads it after the helper's own JSON IPC
    # `loadfile`, and mpv decodes a `\u0000` there and ends the string at it.
    # So `http://127.0.0.1:631<NUL>@p.example.test/x` was the playlist's own
    # host to every rule above and 127.0.0.1:631 to the player -- measured in
    # an unprivileged network namespace through the shipping `playlist` verb
    # and apply_channel: the loopback server got `GET /` carrying the list's
    # Authorization and Cookie, and `udp://0.0.0.0:P<NUL>@239.1.1.1:1` bound
    # 0.0.0.0:P. A control byte has no place in a stream URL, so any C0, DEL
    # or C1 character makes the line no stream URL at all, at parse time and
    # at play time; the NUL is the measured split, the rest are refused so no
    # other parser difference over control bytes has to be found first.
    CONTROL_SPLITS = (
        "http://127.0.0.1:631\x00@p.example.test/x",
        "udp://0.0.0.0:53317\x00@239.1.1.1:1",
        "rtp://0.0.0.0:5004\x00@239.1.1.1:1",
        "http://p.example.test/x\x00y",
        "udp://0.0.0.0:53318\t@239.1.1.1:1",
        "http://p.example.test/a\x7fb",
        "http://p.example.test/a\x85b",
    )

    def test_a_control_byte_in_a_channel_url_makes_it_no_channel_whatever_the_source(self):
        for source in ({"host": "p.example.test", "local": False}, {"host": "", "local": True}):
            lines = ["#EXTM3U"]
            for index, url in enumerate(self.CONTROL_SPLITS):
                lines += ["#EXTINF:-1,C%d" % index,
                          "#KODIPROP:inputstream.adaptive.stream_headers=Authorization=a&Cookie=b", url]
            lines += ["#EXTINF:-1,Ok", "http://p.example.test/ok"]
            # As lines, the way the playlist verb hands them over
            # (playlist_lines splits at LF only): a str would be cut at
            # U+0085 by splitlines before the gate ever saw it.
            result = helper.parse_m3u(lines, source)
            self.assertEqual([c["name"] for c in result["channels"]], ["Ok"], source)
            self.assertIn("%d entries skipped: unsupported URL scheme" % len(self.CONTROL_SPLITS), result["warnings"])
        for url in self.CONTROL_SPLITS:
            self.assertFalse(helper.is_stream_url(url), repr(url))

    def test_a_cached_or_typed_url_with_a_control_byte_is_refused_at_play_time(self):
        """A cache written before the rule, and `play --url`: player_target."""
        with tempfile.TemporaryDirectory() as cache:
            rows = [{"id": "c%d" % i, "name": "C", "group": "G", "url": url,
                     "headers": {"Authorization": "a"}} for i, url in enumerate(self.CONTROL_SPLITS)]
            (pathlib.Path(cache) / "channels.json").write_text(json.dumps({"version": 1, "channels": rows}),
                                                                encoding="utf-8")
            codes = []
            for row in rows:
                with self.assertRaises(helper.HelperError) as caught:
                    helper.player_target(row["id"], "", cache)
                codes.append(caught.exception.code)
            for url in self.CONTROL_SPLITS:
                with self.assertRaises(helper.HelperError) as caught:
                    helper.player_target("", url, cache)
                codes.append(caught.exception.code)
            self.assertEqual(codes, ["unsupported_scheme"] * (2 * len(self.CONTROL_SPLITS)))

    def test_a_header_name_ending_in_a_line_break_is_no_header(self):
        """`_HEADER_NAME` is `^...$`, and `re.match` lets `$` match before a
        final line break, so `Cookie%0A` decoded to a name `Cookie\\n` that
        passed the name check AND the sign-in rule, which compares the name
        exactly, and reached the player's http-header-fields as `Cookie\\n:`.
        The parse refuses such a name as unsafe, and so does the play-time
        reader for a cache written before."""
        text = ("#EXTM3U\n#EXTINF:-1,Cdn\n#KODIPROP:inputstream.adaptive.stream_headers="
                "Cookie%0A=a&Authorization%0A=b&X-Ok=1\nhttp://cdn.example.test/x\n")
        result = helper.parse_m3u(text, {"host": "p.example.test", "local": False})
        self.assertEqual([c.get("headers") for c in result["channels"]], [{"X-Ok": "1"}])
        self.assertIn("dropped header with unsafe name for Cdn", result["warnings"])
        self.assertEqual(helper.header_values({"User-Agent": "UA", "Cookie\n": "a", "X-Ok": "1"}),
                         ("UA", "", ["X-Ok: 1"]))



class PlayTimeGateTest(unittest.TestCase):
    """D-SINK-58 (2026-10-29): player_target runs the parse's host rule and
    sign-in header rule again, against the cache's own record of its
    playlist (cached_source), so a cache nothing checked -- one written
    before the destination rules, whose refresh then failed -- cannot reach
    a LAN or loopback literal its playlist chose, or hand a sign-in header to
    another host. Called for real (rule 12), over caches written here."""

    def cache(self, document):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cache = pathlib.Path(tmp.name) / "cache"
        cache.mkdir(mode=0o700)
        (cache / "channels.json").write_text(json.dumps(document), encoding="utf-8")
        return str(cache)

    CHANNELS = [
        {"id": "t:lan", "name": "LAN", "url": "http://192.168.1.20:5004/auto/v1"},
        {"id": "t:loop", "name": "Loop", "url": "http://127.0.0.1:631/admin"},
        {"id": "t:cdn", "name": "CDN", "url": "http://cdn.example.test/x.m3u8", "headers": {"Cookie": "s=1", "X-Ok": "1"}},
        {"id": "t:own", "name": "Own", "url": "http://p.example.test/live/1.ts", "headers": {"Authorization": "Basic eA=="}},
        {"id": "t:relay", "name": "Relay", "url": "http://127.0.0.1:34400/stream/1", "headers": {"Cookie": "r=1"}},
        {"id": "t:mc", "name": "Multicast", "url": "udp://@239.1.1.1:1234"},
    ]

    def target(self, directory, cid):
        try:
            return helper.player_target(cid, "", directory)
        except helper.HelperError as error:
            return error.code

    def test_a_pre_rules_cache_from_a_public_playlist_refuses_local_literals_and_drops_sign_in_headers(self):
        # The shape 0.15.0 wrote: no sourceClass, no sourceLocal, no sourcePort.
        directory = self.cache({"version": 1, "sourceHost": "p.example.test", "channels": self.CHANNELS})
        got = {}
        for cid in ("t:lan", "t:loop", "t:cdn", "t:own", "t:mc"):
            with mock.patch.object(helper, "cache_dir", lambda d: d):
                result = self.target(directory, cid)
            got[cid] = result if isinstance(result, str) else result["headers"]
        self.assertEqual(got, {"t:lan": "local_address", "t:loop": "local_address", "t:cdn": {"X-Ok": "1"},
                               "t:own": {"Authorization": "Basic eA=="}, "t:mc": {}})

    def test_a_pre_rules_cache_from_a_file_or_a_lan_literal_is_local(self):
        for host in ("local file", "192.168.1.5"):
            with self.subTest(host=host):
                directory = self.cache({"version": 1, "sourceHost": host, "channels": self.CHANNELS})
                with mock.patch.object(helper, "cache_dir", lambda d: d):
                    lan = self.target(directory, "t:lan")
                    cdn = self.target(directory, "t:cdn")
                self.assertEqual(lan["url"], "http://192.168.1.20:5004/auto/v1")
                # A file has no host, and the CDN is not the LAN host: dropped.
                self.assertEqual(cdn["headers"], {"X-Ok": "1"})

    def test_a_cache_written_now_carries_what_play_time_needs(self):
        """A loopback relay (Threadfin, xTeVe): its own port keeps the
        sign-in header; its LAN channel plays (a relay passing an HDHomeRun or
        a TVHeadend stream through); and since D-SINK-57's scope (the lead,
        2026-10-29) a channel on ANOTHER loopback port is refused at play
        time as at parse time -- a cache the parse never saw cannot reach
        another service of this machine either."""
        relay = [dict(c) for c in self.CHANNELS] + [
            {"id": "t:other", "name": "Other", "url": "http://127.0.0.1:631/x", "headers": {"Cookie": "o=1"}},
            {"id": "t:alias", "name": "Alias", "url": "http://localhost:34400/stream/2"}]
        directory = self.cache({"version": 1, "sourceHost": "127.0.0.1", "sourceClass": "loopback",
                                "sourcePort": 34400, "sourceLocal": True, "channels": relay})
        with mock.patch.object(helper, "cache_dir", lambda d: d):
            got = {cid: self.target(directory, cid) for cid in ("t:relay", "t:other", "t:loop", "t:lan", "t:alias")}
        self.assertEqual(got["t:relay"]["headers"], {"Cookie": "r=1"})
        self.assertEqual((got["t:other"], got["t:loop"]), ("local_address", "local_address"))
        self.assertEqual(got["t:lan"]["url"], "http://192.168.1.20:5004/auto/v1")
        # The rule is the relay's PORT (the lead's wording): another spelling
        # of this machine at that port plays; its sign-in headers are another
        # host's (own_host_match), which this one has none of.
        self.assertEqual(got["t:alias"]["url"], "http://localhost:34400/stream/2")
        # Without the port (a cache from before D-SINK-57) no loopback port is
        # the relay's, so its own channel fails closed until the next refresh
        # writes the port; the LAN channel still plays.
        directory = self.cache({"version": 1, "sourceHost": "127.0.0.1", "sourceClass": "loopback",
                                "channels": relay})
        with mock.patch.object(helper, "cache_dir", lambda d: d):
            self.assertEqual(self.target(directory, "t:relay"), "local_address")
            self.assertEqual(self.target(directory, "t:lan")["url"], "http://192.168.1.20:5004/auto/v1")

    def test_the_cli_url_meets_the_listening_rule_only(self):
        self.assertEqual(helper.player_target("", "http://192.168.1.20:5004/auto/v1", "/nonexistent")["url"],
                         "http://192.168.1.20:5004/auto/v1")
        with self.assertRaises(helper.HelperError) as caught:
            helper.player_target("", "udp://0.0.0.0:1234", "/nonexistent")
        self.assertEqual(caught.exception.code, "unsupported_scheme")

    def test_mutating_the_play_time_gate_away_lets_the_lan_literal_through(self):
        """Rule 11: with stream_host_refused answering False, the pre-rules
        cache's LAN channel resolves -- so the first test is the gate's."""
        directory = self.cache({"version": 1, "sourceHost": "p.example.test", "channels": self.CHANNELS})
        with mock.patch.object(helper, "cache_dir", lambda d: d), \
                mock.patch.object(helper, "stream_host_refused", lambda url, source: False):
            self.assertEqual(self.target(directory, "t:lan")["url"], "http://192.168.1.20:5004/auto/v1")



if __name__ == "__main__":
    unittest.main()

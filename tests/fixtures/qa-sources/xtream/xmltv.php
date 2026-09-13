<?xml version="1.0" encoding="UTF-8"?>
<!--
  QA fixture: the XMLTV an Xtream panel returns from xmltv.php (docs/QA-SOURCES.md, section 8).
  Served next to get.php by the harness fixture server; the query string is dropped by
  python3 -m http.server, so /xmltv.php?username=user&password=pa%20ss serves this file.
  One evergreen programme per live channel (2026-01-01Z .. 2030-01-01Z): "Now:" rows without "Next:".
-->
<tv generator-info-name="omarchy-iptv-qa" source-info-name="qa-sources-xtream">
  <channel id="qa.x.one"><display-name>Xtream Live One</display-name></channel>
  <channel id="qa.x.two"><display-name>Xtream Live Two</display-name></channel>
  <programme start="20260101000000 +0000" stop="20300101000000 +0000" channel="qa.x.one"><title>Xtream Evergreen One</title></programme>
  <programme start="20260101000000 +0000" stop="20300101000000 +0000" channel="qa.x.two"><title>Xtream Evergreen Two</title></programme>
</tv>

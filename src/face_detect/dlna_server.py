"""DLNA/UPnP Media Server for Arquive.

Broadcasts itself on the LAN via SSDP so Apple TV (via Infuse/VLC),
Samsung TV, LG TV, Fire TV, and any DLNA client discovers it automatically.
Serves the media library as a UPnP Content Directory with folder browsing.

How it works:
  1. SSDP: multicast advertisement on 239.255.255.250:1900
  2. HTTP: serves UPnP device description XML + content directory SOAP
  3. Media: streams files directly via Flask /file?path= (no transcoding)
  4. 4K: full support — modern TVs decode HEVC/H.264/VP9 in hardware

Apple TV: use Infuse, VLC, or any DLNA app to see "Arquive Media Server"
Windows: open Network in Explorer, Arquive appears as a media device
Linux: use VLC > Universal Plug'n'Play

Dependencies: socket (stdlib), threading, http.server, xml.etree
"""

from __future__ import annotations

import html
import logging
import mimetypes
import os
import re
import socket
import struct
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import quote

log = logging.getLogger(__name__)

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
DEVICE_TYPE = "urn:schemas-upnp-org:device:MediaServer:1"
SERVICE_TYPE = "urn:schemas-upnp-org:service:ContentDirectory:1"


def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class DLNAServer:
    """Full DLNA/UPnP Media Server with SSDP discovery."""

    def __init__(self, db: Any, config: Any, http_port: int = 64532) -> None:
        self.db = db
        self.config = config
        self.friendly_name = config.dlna.friendly_name
        self.http_port = http_port
        self.lan_ip = _get_lan_ip()
        self.base_url = f"http://{self.lan_ip}:{http_port}"
        self.media_url = f"http://{self.lan_ip}:{config.server.port}"
        self._ssdp_thread: threading.Thread | None = None
        self._http_thread: threading.Thread | None = None
        self._http_server: HTTPServer | None = None
        self._running = False
        self._uuid = f"uuid:arquive-{self.lan_ip.replace('.', '-')}"

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        handler = self._make_handler()
        self._http_server = HTTPServer(("0.0.0.0", self.http_port), handler)
        self._http_thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
        self._http_thread.start()

        self._ssdp_thread = threading.Thread(target=self._ssdp_loop, daemon=True)
        self._ssdp_thread.start()

        log.info("DLNA server '%s' started on %s:%d (media at %s)",
                 self.friendly_name, self.lan_ip, self.http_port, self.media_url)

    def stop(self) -> None:
        self._running = False
        if self._http_server:
            self._http_server.shutdown()
        log.info("DLNA server stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _ssdp_loop(self) -> None:
        """Broadcast SSDP alive + respond to M-SEARCH."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        sock.settimeout(2)

        alive = (
            f"NOTIFY * HTTP/1.1\r\nHOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
            f"CACHE-CONTROL: max-age=1800\r\nLOCATION: {self.base_url}/description.xml\r\n"
            f"NT: {DEVICE_TYPE}\r\nNTS: ssdp:alive\r\n"
            f"SERVER: Arquive/1.0 UPnP/1.1\r\nUSN: {self._uuid}::{DEVICE_TYPE}\r\n\r\n"
        )

        # Join multicast for M-SEARCH
        msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            msock.bind(("", SSDP_PORT))
            mreq = struct.pack("4sL", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
            msock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            msock.settimeout(2)
        except OSError:
            log.warning("Could not bind SSDP port %d", SSDP_PORT)
            msock = None

        while self._running:
            try:
                sock.sendto(alive.encode(), (SSDP_ADDR, SSDP_PORT))
            except Exception:
                pass

            if msock:
                try:
                    data, addr = msock.recvfrom(4096)
                    msg = data.decode(errors="replace")
                    if "M-SEARCH" in msg and ("ssdp:all" in msg or "MediaServer" in msg):
                        resp = (
                            f"HTTP/1.1 200 OK\r\nLOCATION: {self.base_url}/description.xml\r\n"
                            f"ST: {DEVICE_TYPE}\r\nUSN: {self._uuid}::{DEVICE_TYPE}\r\n"
                            f"SERVER: Arquive/1.0 UPnP/1.1\r\nCACHE-CONTROL: max-age=1800\r\n\r\n"
                        )
                        sock.sendto(resp.encode(), addr)
                except socket.timeout:
                    pass
                except Exception:
                    pass

            time.sleep(30)

        sock.close()
        if msock:
            msock.close()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                if self.path == "/description.xml":
                    self._send_xml(self._device_xml())
                elif self.path == "/ContentDirectory.xml":
                    self._send_xml(self._scpd_xml())
                else:
                    self.send_error(404)

            def do_POST(self):
                if "/ContentDirectory" in self.path:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode(errors="replace") if length else ""
                    if "Browse" in body:
                        obj_match = re.search(r"<ObjectID>([^<]*)</ObjectID>", body)
                        oid = obj_match.group(1) if obj_match else "0"
                        self._browse(oid)
                    elif "GetSystemUpdateID" in body:
                        self._send_xml(
                            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                            '<s:Body><u:GetSystemUpdateIDResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
                            '<Id>1</Id></u:GetSystemUpdateIDResponse></s:Body></s:Envelope>'
                        )
                    else:
                        self.send_error(501)
                else:
                    self.send_error(404)

            def _device_xml(self) -> str:
                return f"""<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion><major>1</major><minor>1</minor></specVersion>
<device>
  <deviceType>{DEVICE_TYPE}</deviceType>
  <friendlyName>{html.escape(server.friendly_name)}</friendlyName>
  <manufacturer>Arquive</manufacturer>
  <modelName>Arquive Media Server</modelName>
  <modelDescription>Personal Media Archive</modelDescription>
  <modelNumber>1.0</modelNumber>
  <UDN>{server._uuid}</UDN>
  <serviceList>
    <service>
      <serviceType>{SERVICE_TYPE}</serviceType>
      <serviceId>urn:upnp-org:serviceId:ContentDirectory</serviceId>
      <SCPDURL>/ContentDirectory.xml</SCPDURL>
      <controlURL>/ContentDirectory/control</controlURL>
      <eventSubURL>/ContentDirectory/event</eventSubURL>
    </service>
  </serviceList>
</device></root>"""

            def _scpd_xml(self) -> str:
                return """<?xml version="1.0" encoding="UTF-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
<specVersion><major>1</major><minor>0</minor></specVersion>
<actionList>
  <action><name>Browse</name>
    <argumentList>
      <argument><name>ObjectID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_ObjectID</relatedStateVariable></argument>
      <argument><name>BrowseFlag</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_BrowseFlag</relatedStateVariable></argument>
      <argument><name>Filter</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Filter</relatedStateVariable></argument>
      <argument><name>StartingIndex</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Index</relatedStateVariable></argument>
      <argument><name>RequestedCount</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>
      <argument><name>SortCriteria</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_SortCriteria</relatedStateVariable></argument>
      <argument><name>Result</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Result</relatedStateVariable></argument>
      <argument><name>NumberReturned</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>
      <argument><name>TotalMatches</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>
      <argument><name>UpdateID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_UpdateID</relatedStateVariable></argument>
    </argumentList>
  </action>
  <action><name>GetSystemUpdateID</name>
    <argumentList>
      <argument><name>Id</name><direction>out</direction><relatedStateVariable>SystemUpdateID</relatedStateVariable></argument>
    </argumentList>
  </action>
</actionList>
<serviceStateTable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_ObjectID</name><dataType>string</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_Result</name><dataType>string</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_BrowseFlag</name><dataType>string</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_Filter</name><dataType>string</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_SortCriteria</name><dataType>string</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_Index</name><dataType>ui4</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_Count</name><dataType>ui4</dataType></stateVariable>
  <stateVariable sendEvents="no"><name>A_ARG_TYPE_UpdateID</name><dataType>ui4</dataType></stateVariable>
  <stateVariable sendEvents="yes"><name>SystemUpdateID</name><dataType>ui4</dataType></stateVariable>
</serviceStateTable>
</scpd>"""

            def _browse(self, object_id: str):
                items = ""
                count = 0

                if object_id == "0":
                    libs = server.db.get_libraries()
                    for lib in libs:
                        items += (
                            f'<container id="lib_{lib["id"]}" parentID="0" restricted="true" '
                            f'childCount="{lib.get("file_count", 0)}">'
                            f'<dc:title>{html.escape(lib["name"])}</dc:title>'
                            f'<upnp:class>object.container.storageFolder</upnp:class>'
                            f'</container>'
                        )
                        count += 1

                elif object_id.startswith("lib_"):
                    lib_id = int(object_id.split("_")[1])
                    files = server.db.get_files(library_id=lib_id, limit=500)
                    for f in files:
                        mime = f.get("mime_type") or "application/octet-stream"
                        url = f'{server.media_url}/file?path={quote(f["path"])}'
                        cls = (
                            "object.item.videoItem" if mime.startswith("video/") else
                            "object.item.imageItem.photo" if mime.startswith("image/") else
                            "object.item.audioItem.musicTrack" if mime.startswith("audio/") else
                            "object.item.textItem"
                        )
                        res_attr = f'protocolInfo="http-get:*:{mime}:*" size="{f.get("size", 0)}"'
                        if f.get("width") and f.get("height"):
                            res_attr += f' resolution="{f["width"]}x{f["height"]}"'
                        if f.get("duration"):
                            h, m, s = int(f["duration"] // 3600), int(f["duration"] % 3600 // 60), int(f["duration"] % 60)
                            res_attr += f' duration="{h}:{m:02d}:{s:02d}"'

                        items += (
                            f'<item id="f_{f["id"]}" parentID="{object_id}" restricted="true">'
                            f'<dc:title>{html.escape(f["name"])}</dc:title>'
                            f'<upnp:class>{cls}</upnp:class>'
                            f'<res {res_attr}>{html.escape(url)}</res>'
                            f'</item>'
                        )
                        count += 1

                didl = (
                    '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                    f'{items}</DIDL-Lite>'
                )

                soap = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                    '<s:Body><u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
                    f'<Result>{html.escape(didl)}</Result>'
                    f'<NumberReturned>{count}</NumberReturned>'
                    f'<TotalMatches>{count}</TotalMatches>'
                    f'<UpdateID>1</UpdateID>'
                    f'</u:BrowseResponse></s:Body></s:Envelope>'
                )
                self._send_xml(soap)

            def _send_xml(self, content: str):
                data = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/xml; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler


def start_dlna_server(db: Any, config: Any) -> DLNAServer | None:
    """Start DLNA server if enabled in config."""
    if not config.dlna.enabled:
        return None
    server = DLNAServer(db, config)
    server.start()
    return server

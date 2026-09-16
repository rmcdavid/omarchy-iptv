# Minimal D-Bus client, Python 3 standard library only.
# No third-party imports (CLAUDE.md rule 3). ASCII only (rule 8).
import os
import socket
import struct

HEADER_PATH = 1
HEADER_INTERFACE = 2
HEADER_MEMBER = 3
HEADER_ERROR_NAME = 4
HEADER_REPLY_SERIAL = 5
HEADER_DESTINATION = 6
HEADER_SIGNATURE = 8


class DBusError(Exception):
    pass


class DBusTimeout(DBusError):
    pass


class _Writer(object):
    def __init__(self):
        self.buf = bytearray()

    def pad(self, n):
        while len(self.buf) % n:
            self.buf.append(0)

    def byte(self, v):
        self.buf.append(v & 0xFF)

    def uint32(self, v):
        self.pad(4)
        self.buf += struct.pack("<I", v)

    def string(self, s, kind="s"):
        raw = s.encode("utf-8")
        if kind == "g":
            self.buf.append(len(raw))
        else:
            self.uint32(len(raw))
        self.buf += raw
        self.buf.append(0)


class _Reader(object):
    def __init__(self, data, offset=0):
        self.d = data
        self.o = offset

    def pad(self, n):
        while self.o % n:
            self.o += 1

    def take(self, n):
        v = self.d[self.o:self.o + n]
        self.o += n
        return v

    def basic(self, code):
        if code == "y":
            return self.take(1)[0]
        if code == "b":
            self.pad(4)
            return struct.unpack("<I", self.take(4))[0] != 0
        if code == "n":
            self.pad(2)
            return struct.unpack("<h", self.take(2))[0]
        if code == "q":
            self.pad(2)
            return struct.unpack("<H", self.take(2))[0]
        if code in ("i", "h"):
            self.pad(4)
            return struct.unpack("<i", self.take(4))[0]
        if code == "u":
            self.pad(4)
            return struct.unpack("<I", self.take(4))[0]
        if code == "x":
            self.pad(8)
            return struct.unpack("<q", self.take(8))[0]
        if code == "t":
            self.pad(8)
            return struct.unpack("<Q", self.take(8))[0]
        if code == "d":
            self.pad(8)
            return struct.unpack("<d", self.take(8))[0]
        if code in ("s", "o"):
            self.pad(4)
            n = struct.unpack("<I", self.take(4))[0]
            v = self.take(n).decode("utf-8")
            self.take(1)
            return v
        if code == "g":
            n = self.take(1)[0]
            v = self.take(n).decode("utf-8")
            self.take(1)
            return v
        raise DBusError("unsupported type code " + code)

    def value(self, sig, i=0):
        """Read one complete value of signature sig starting at sig[i].
        Returns (python_value, next_index_into_sig)."""
        code = sig[i]
        if code == "a":
            elem_start = i + 1
            elem_end = _sig_end(sig, elem_start)
            self.pad(4)
            nbytes = struct.unpack("<I", self.take(4))[0]
            elem = sig[elem_start]
            if elem == "{" or elem == "(":
                self.pad(8)
            elif elem in ("x", "t", "d"):
                self.pad(8)
            end = self.o + nbytes
            out = []
            while self.o < end:
                v, _ = self.value(sig, elem_start)
                out.append(v)
            self.o = end
            if elem == "{":
                return dict(out), elem_end
            return out, elem_end
        if code == "(" or code == "{":
            close = ")" if code == "(" else "}"
            self.pad(8)
            j = i + 1
            fields = []
            while sig[j] != close:
                v, j = self.value(sig, j)
                fields.append(v)
            if code == "{":
                return (fields[0], fields[1]), j + 1
            return tuple(fields), j + 1
        if code == "v":
            vsig = self.basic("g")
            v, _ = self.value(vsig, 0)
            return v, i + 1
        return self.basic(code), i + 1


def _sig_end(sig, i):
    code = sig[i]
    if code == "a":
        return _sig_end(sig, i + 1)
    if code in "({":
        close = ")" if code == "(" else "}"
        depth = 0
        j = i
        while True:
            if sig[j] in "({":
                depth += 1
            elif sig[j] in ")}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
    return i + 1


class Bus(object):
    def __init__(self, address, timeout=10.0):
        path = None
        for part in address.split(";"):
            if part.startswith("unix:"):
                for kv in part[5:].split(","):
                    if kv.startswith("path="):
                        path = kv[5:]
                    elif kv.startswith("abstract="):
                        path = "\0" + kv[9:]
        if path is None:
            raise DBusError("no unix socket in address: " + address)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.serial = 0
        self._rx = bytearray()
        self._auth()
        self.unique_name = self.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", "Hello")[0]

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _auth(self):
        uid_hex = str(os.getuid()).encode("ascii").hex().encode("ascii")
        self.sock.sendall(b"\0AUTH EXTERNAL " + uid_hex + b"\r\n")
        line = self._readline()
        if not line.startswith(b"OK"):
            raise DBusError("auth failed: " + repr(line))
        self.sock.sendall(b"BEGIN\r\n")

    def _readline(self):
        out = bytearray()
        while not out.endswith(b"\r\n"):
            c = self.sock.recv(1)
            if not c:
                raise DBusError("eof during auth")
            out += c
        return bytes(out)

    def _recv_exact(self, n):
        while len(self._rx) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise DBusError("eof on bus")
            self._rx += chunk
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def call(self, dest, path, iface, member, signature="", args=(), timeout=10.0):
        self.serial += 1
        serial = self.serial
        body = _Writer()
        if signature:
            i = 0
            for a in args:
                code = signature[i]
                if code in ("s", "o"):
                    body.string(a, code)
                elif code == "u":
                    body.uint32(a)
                elif code == "i":
                    body.pad(4)
                    body.buf += struct.pack("<i", a)
                else:
                    raise DBusError("unsupported arg type " + code)
                i = _sig_end(signature, i)
        fields = [(HEADER_PATH, "o", path), (HEADER_INTERFACE, "s", iface),
                  (HEADER_MEMBER, "s", member), (HEADER_DESTINATION, "s", dest)]
        if signature:
            fields.append((HEADER_SIGNATURE, "g", signature))
        fa = _Writer()
        for code, vtype, val in fields:
            fa.pad(8)
            fa.byte(code)
            fa.string(vtype, "g")
            if vtype == "g":
                fa.string(val, "g")
            else:
                fa.string(val, "s")
        hdr = bytearray()
        hdr += struct.pack("<BBBBII", ord("l"), 1, 0, 1, len(body.buf), serial)
        hdr += struct.pack("<I", len(fa.buf))
        hdr += fa.buf
        while len(hdr) % 8:
            hdr.append(0)
        self.sock.settimeout(timeout)
        self.sock.sendall(bytes(hdr) + bytes(body.buf))
        while True:
            try:
                msg = self._read_message()
            except (socket.timeout, TimeoutError):
                raise DBusTimeout("no reply to %s.%s within %.1fs" % (iface, member, timeout))
            if msg is None:
                continue
            mtype, rserial, ename, sig, payload, off = msg
            if rserial != serial:
                continue
            if mtype == 3:
                raise DBusError(ename + ": " + repr(self._decode(sig, payload, off)))
            return self._decode(sig, payload, off)

    def _decode(self, sig, payload, off):
        if not sig:
            return ()
        r = _Reader(payload, off)
        out = []
        i = 0
        while i < len(sig):
            v, i = r.value(sig, i)
            out.append(v)
        return tuple(out)

    def _read_message(self):
        head = self._recv_exact(12)
        endian, mtype, flags, ver, blen, serial = struct.unpack("<BBBBII", head)
        if endian != ord("l"):
            raise DBusError("big-endian message not supported")
        falen = struct.unpack("<I", self._recv_exact(4))[0]
        fa = self._recv_exact(falen)
        pad = (8 - (falen % 8)) % 8
        if pad:
            self._recv_exact(pad)
        body = self._recv_exact(blen)
        r = _Reader(fa, 0)
        rserial = None
        ename = None
        sig = ""
        while r.o < len(fa):
            r.pad(8)
            code = r.basic("y")
            vtype = r.basic("g")
            val, _ = r.value(vtype, 0)
            if code == HEADER_REPLY_SERIAL:
                rserial = val
            elif code == HEADER_ERROR_NAME:
                ename = val
            elif code == HEADER_SIGNATURE:
                sig = val
        return (mtype, rserial, ename, sig, body, 0)


def session_address():
    a = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if a:
        return a
    return "unix:path=" + os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()) + "/bus"


def a11y_address():
    a = os.environ.get("AT_SPI_BUS_ADDRESS")
    if a:
        return a
    b = Bus(session_address())
    try:
        return b.call("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress")[0]
    finally:
        b.close()

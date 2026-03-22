import gzip
import socket
import ssl
import zlib
from typing import Dict, Tuple

ALLOWED_PROTOCOLS = ("http", "https", "view-source")
MAX_REDIRECTS = 10
_response_cache: Dict[str, str] = {}

from .net.cookies import CookieJar  # noqa: F401, E402

# ---------------------------------------------------------------------------
# URL class
# ---------------------------------------------------------------------------

def _read_chunked(stream) -> bytes:
    body = bytearray()
    while True:
        line = stream.readline()
        if not line:
            break
        size_str = line.strip()
        if not size_str:
            continue
        try:
            chunk_size = int(size_str, 16)
        except ValueError:
            break
        if chunk_size == 0:
            stream.readline()
            break
        chunk = stream.read(chunk_size)
        body.extend(chunk)
        stream.readline()
    return bytes(body)


def _decompress(data: bytes, encoding: str) -> str:
    try:
        if "gzip" in encoding:
            data = gzip.decompress(data)
        elif "deflate" in encoding:
            try:
                data = zlib.decompress(data)
            except zlib.error:
                data = zlib.decompress(data, -zlib.MAX_WBITS)
    except Exception:
        pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


class Url:
    def __init__(self, url: str) -> None:
        self.view_source = False
        if url.startswith("view-source:"):
            self.view_source = True
            url = url[len("view-source:"):]

        self.url = url
        self.protocol, self.hostname, self.path, self.port = self._parse_url()

    def request(self, **headers) -> Tuple[int, Dict[str, str], str]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if self.protocol == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=self.hostname)

        sock.connect((self.hostname, self.port))

        cookie_header = CookieJar.get().get_header(self.hostname, self.path)
        if cookie_header:
            headers.setdefault("Cookie", cookie_header)
        headers.setdefault("Accept-Encoding", "gzip, deflate")

        sock.send(self._build_request(headers).encode())

        raw = sock.makefile("rb")
        statusline = raw.readline().decode("utf-8", errors="replace")
        version, status, explanation = statusline.split(" ", 2)
        status = int(status)

        response_headers: Dict[str, str] = {}
        while True:
            line = raw.readline().decode("utf-8", errors="replace")
            if line in ("\r\n", "\n", ""):
                break
            if ":" not in line:
                continue
            header, value = line.split(":", 1)
            key = header.casefold()
            if key == "set-cookie":
                CookieJar.get().set_from_header(self.hostname, value.strip())
            response_headers[key] = value.strip()

        transfer = response_headers.get("transfer-encoding", "")
        content_len = response_headers.get("content-length", "")

        if "chunked" in transfer:
            raw_body = _read_chunked(raw)
        elif content_len:
            raw_body = raw.read(int(content_len))
        else:
            raw_body = raw.read()
        sock.close()

        encoding = response_headers.get("content-encoding", "")
        body = _decompress(raw_body, encoding)

        return status, response_headers, body

    def fetch(self, use_cache: bool = True) -> str:
        """Fetch the URL, following redirects. Returns the response body."""
        if use_cache and self.url in _response_cache:
            return _response_cache[self.url]

        redirects = 0
        url = self
        while True:
            status, headers, body = url.request()
            if 300 <= status < 400 and "location" in headers:
                if redirects >= MAX_REDIRECTS:
                    raise Exception("Too many redirects")
                location = headers["location"]
                if location.startswith("/"):
                    location = url.origin + location
                url = Url(location)
                redirects += 1
            else:
                break

        _response_cache[self.url] = body
        return body

    def fetch_binary(self) -> bytes:
        """Fetch raw bytes (for images)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.protocol == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=self.hostname)
        sock.connect((self.hostname, self.port))
        sock.send(self._build_request({}).encode())

        response = sock.makefile("rb")
        statusline = response.readline().decode()
        version, status, explanation = statusline.split(" ", 2)

        while True:
            line = response.readline().decode()
            if line in ("\r\n", "\n", ""):
                break

        data = response.read()
        sock.close()
        return data

    def _build_request(self, headers: dict, method: str = "GET", body: str = "") -> str:
        request = f"{method} {self.path} HTTP/1.1\r\n"
        request += f"Host: {self.hostname}\r\n"
        request += "Connection: close\r\n"
        request += "User-Agent: Pybrowser/1.0\r\n"
        if body:
            request += f"Content-Length: {len(body.encode())}\r\n"
            request += "Content-Type: application/x-www-form-urlencoded\r\n"
        for key, value in headers.items():
            request += f"{key}: {value}\r\n"
        request += "\r\n"
        if body:
            request += body
        return request

    @property
    def origin(self) -> str:
        default_port = (self.protocol == "https" and self.port == 443) or \
                       (self.protocol == "http" and self.port == 80)
        if default_port:
            return f"{self.protocol}://{self.hostname}"
        return f"{self.protocol}://{self.hostname}:{self.port}"

    def resolve(self, relative: str) -> str:
        """Resolve a relative URL against this URL."""
        if relative.startswith("#"):
            return self.url + relative
        if "://" in relative:
            return relative
        if relative.startswith("//"):
            return self.protocol + ":" + relative
        if relative.startswith("/"):
            return self.origin + relative
        dir_path = self.path.rsplit("/", 1)[0] if "/" in self.path else ""
        return self.origin + dir_path + "/" + relative

    def _parse_url(self) -> Tuple[str, str, str, int]:
        protocol, rest = self.url.split("://", 1)
        assert protocol in ("http", "https"), f"Unknown protocol: {protocol}"

        if "/" in rest:
            hostname, path = rest.split("/", 1)
            path = "/" + path
        else:
            hostname, path = rest, "/"

        if ":" in hostname:
            hostname, port_str = hostname.split(":", 1)
            port = int(port_str)
        else:
            port = 80 if protocol == "http" else 443

        return protocol, hostname, path or "/", port

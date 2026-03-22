import socket
import ssl
from typing import Dict, Optional, Tuple

ALLOWED_PROTOCOLS = ("http", "https", "view-source")
MAX_REDIRECTS = 10

_response_cache: Dict[str, str] = {}


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
        sock.send(self._build_request(headers).encode())

        response = sock.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        status = int(status)

        response_headers: Dict[str, str] = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        body = response.read()
        sock.close()

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

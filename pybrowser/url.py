import json
import os
import socket
import ssl
from typing import Dict, List, Optional, Tuple

ALLOWED_PROTOCOLS = ("http", "https", "view-source")
MAX_REDIRECTS = 10
COOKIE_FILE = os.path.expanduser("~/.pybrowser/cookies.json")

_response_cache: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Cookie jar
# ---------------------------------------------------------------------------

class CookieJar:
    _instance: Optional["CookieJar"] = None

    def __init__(self) -> None:
        self._cookies: Dict[str, Dict[str, dict]] = {}
        self._load()

    @classmethod
    def get(cls) -> "CookieJar":
        if cls._instance is None:
            cls._instance = CookieJar()
        return cls._instance

    def _load(self) -> None:
        try:
            with open(COOKIE_FILE) as f:
                self._cookies = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._cookies = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            json.dump(self._cookies, f)

    def set_from_header(self, domain: str, header: str) -> None:
        parts = header.split(";")
        if not parts:
            return
        name_val = parts[0].strip()
        if "=" not in name_val:
            return
        name, value = name_val.split("=", 1)
        name = name.strip()
        value = value.strip()

        cookie: dict = {"value": value}
        for part in parts[1:]:
            part = part.strip().lower()
            if part.startswith("path="):
                cookie["path"] = part[5:]
            elif part.startswith("domain="):
                cookie["domain"] = part[7:].lstrip(".")
            elif part == "httponly":
                cookie["httponly"] = True
            elif part == "secure":
                cookie["secure"] = True
            elif part.startswith("samesite="):
                cookie["samesite"] = part[9:]

        if domain not in self._cookies:
            self._cookies[domain] = {}
        self._cookies[domain][name] = cookie
        self._save()

    def get_header(self, domain: str, path: str = "/") -> str:
        pairs: List[str] = []
        for d in (domain, "." + domain):
            for name, cookie in self._cookies.get(d, {}).items():
                cookie_path = cookie.get("path", "/")
                if path.startswith(cookie_path):
                    pairs.append(f"{name}={cookie['value']}")
        parent = ".".join(domain.split(".")[-2:])
        if parent != domain:
            for name, cookie in self._cookies.get(parent, {}).items():
                cookie_path = cookie.get("path", "/")
                if path.startswith(cookie_path):
                    pairs.append(f"{name}={cookie['value']}")
        return "; ".join(pairs)

    def get_all(self, domain: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for d in (domain, "." + domain):
            for name, cookie in self._cookies.get(d, {}).items():
                result[name] = cookie["value"]
        return result

    def clear(self, domain: Optional[str] = None) -> None:
        if domain:
            self._cookies.pop(domain, None)
        else:
            self._cookies = {}
        self._save()


# ---------------------------------------------------------------------------
# URL class
# ---------------------------------------------------------------------------

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
            key = header.casefold()
            if key == "set-cookie":
                CookieJar.get().set_from_header(self.hostname, value.strip())
            response_headers[key] = value.strip()

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

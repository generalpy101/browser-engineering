"""Cookie jar: parse Set-Cookie headers, store per domain, send with requests."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

COOKIE_FILE = os.path.expanduser("~/.pybrowser/cookies.json")


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
        name, value = name.strip(), value.strip()
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
        if domain not in self._cookies:
            self._cookies[domain] = {}
        self._cookies[domain][name] = cookie
        self._save()

    def get_header(self, domain: str, path: str = "/") -> str:
        pairs: List[str] = []
        for d in (domain, "." + domain):
            for name, cookie in self._cookies.get(d, {}).items():
                if path.startswith(cookie.get("path", "/")):
                    pairs.append(f"{name}={cookie['value']}")
        parent = ".".join(domain.split(".")[-2:])
        if parent != domain:
            for name, cookie in self._cookies.get(parent, {}).items():
                if path.startswith(cookie.get("path", "/")):
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

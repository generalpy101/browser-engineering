"""Simple adblocker: block requests matching filter patterns."""
from __future__ import annotations

import os
import re
from typing import List, Set

FILTERS_FILE = os.path.expanduser("~/.pybrowser/adblock_filters.txt")

DEFAULT_FILTERS = [
    "||ads.",
    "||ad.",
    "||doubleclick.net",
    "||googlesyndication.com",
    "||googleadservices.com",
    "||google-analytics.com",
    "||facebook.com/tr",
    "||analytics.",
    "||tracker.",
    "||tracking.",
    "||adserver.",
    "||banner.",
    "||popup.",
    "/ads/",
    "/ad/",
    "/advertisement/",
    "/_ads/",
    "/adsbygoogle",
    ".doubleclick.net",
    "google-analytics.com/analytics.js",
    "googletag",
    "pagead",
    "adsense",
]


class AdBlocker:
    _instance = None

    def __init__(self) -> None:
        self.enabled = True
        self.blocked_count = 0
        self._patterns: List[str] = []
        self._blocked_domains: Set[str] = set()
        self._load_filters()

    @classmethod
    def get(cls) -> "AdBlocker":
        if cls._instance is None:
            cls._instance = AdBlocker()
        return cls._instance

    def _load_filters(self) -> None:
        self._patterns = list(DEFAULT_FILTERS)
        try:
            with open(FILTERS_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("!") and not line.startswith("["):
                        self._patterns.append(line)
        except FileNotFoundError:
            pass

        for p in self._patterns:
            if p.startswith("||"):
                domain = p[2:].split("/")[0].split("^")[0]
                self._blocked_domains.add(domain)

    def should_block(self, url: str) -> bool:
        if not self.enabled:
            return False
        url_lower = url.lower()

        for domain in self._blocked_domains:
            if domain in url_lower:
                self.blocked_count += 1
                return True

        for pattern in self._patterns:
            if pattern.startswith("||"):
                continue
            if pattern.startswith("/") and pattern.endswith("/"):
                try:
                    if re.search(pattern[1:-1], url_lower):
                        self.blocked_count += 1
                        return True
                except re.error:
                    pass
            elif pattern in url_lower:
                self.blocked_count += 1
                return True

        return False

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def add_filter(self, pattern: str) -> None:
        self._patterns.append(pattern)
        if pattern.startswith("||"):
            domain = pattern[2:].split("/")[0]
            self._blocked_domains.add(domain)

    def save_filters(self) -> None:
        os.makedirs(os.path.dirname(FILTERS_FILE), exist_ok=True)
        custom = [p for p in self._patterns if p not in DEFAULT_FILTERS]
        if custom:
            with open(FILTERS_FILE, "w") as f:
                for p in custom:
                    f.write(p + "\n")

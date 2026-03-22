"""Per-tab state: DOM, styles, scroll, display list, JS runtime."""
from __future__ import annotations

from typing import Any, List, Optional

from .html_parser import Element
from .layout import DocumentLayout
from .paint import DisplayCommand


class Tab:
    def __init__(self, url: str = "") -> None:
        self.url = url
        self.title = "New Tab"
        self.scroll = 0
        self.max_y = 0
        self.display_list: List[DisplayCommand] = []
        self.document: Optional[DocumentLayout] = None
        self.dom: Optional[Element] = None
        self.rules: list = []
        self.current_url: Any = None
        self.history: List[str] = []
        self.forward_stack: List[str] = []
        self.body_bg = "#ffffff"
        self.js_runtime: Any = None
        self.focused_input: Optional[Element] = None
        self.timers: list = []

        self.find_text = ""
        self.find_matches: List[tuple] = []
        self.find_index = 0

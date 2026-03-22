"""DevTools panel: DOM inspector, console, network log."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from .renderer import SDLRenderer

from .html_parser import Element, Text


class DevTools:
    def __init__(self) -> None:
        self.visible = False
        self.active_tab = "dom"
        self.console_lines: List[tuple] = []
        self.network_log: List[dict] = []
        self.scroll = 0
        self.panel_width = 400
        self._selected_node: Any = None

    def toggle(self) -> None:
        self.visible = not self.visible

    def log(self, level: str, msg: str) -> None:
        self.console_lines.append((level, msg, time.strftime("%H:%M:%S")))
        if len(self.console_lines) > 200:
            self.console_lines = self.console_lines[-200:]

    def log_network(self, method: str, url: str, status: int, size: int, duration_ms: int) -> None:
        self.network_log.append({
            "method": method, "url": url, "status": status,
            "size": size, "time": duration_ms,
        })
        if len(self.network_log) > 100:
            self.network_log = self.network_log[-100:]

    def draw(self, renderer: SDLRenderer, x: int, y: int, w: int, h: int) -> None:
        if not self.visible:
            return
        r = renderer
        f = r.get_font(12, "normal", "roman", "Courier")
        fb = r.get_font(12, "bold", "roman", "Courier")

        r.draw_rect(x, y, w, h, "#1e1e1e")
        r.draw_line(x, y, x, y + h, "#444444", 1)

        tab_names = [("dom", "Elements"), ("console", "Console"), ("network", "Network")]
        tx = x + 4
        for tid, label in tab_names:
            tw = f.measure(label) + 16
            bg = "#2d2d2d" if tid == self.active_tab else "#1e1e1e"
            r.draw_rect(tx, y + 2, tw, 20, bg)
            color = "#ffffff" if tid == self.active_tab else "#888888"
            r.draw_text(tx + 8, y + 5, label, f, color)
            tx += tw + 2

        r.draw_line(x, y + 24, x + w, y + 24, "#444444", 1)
        content_y = y + 26

        if self.active_tab == "dom":
            self._draw_dom(r, f, x + 4, content_y, w - 8, h - 26)
        elif self.active_tab == "console":
            self._draw_console(r, f, x + 4, content_y, w - 8, h - 26)
        elif self.active_tab == "network":
            self._draw_network(r, f, fb, x + 4, content_y, w - 8, h - 26)

    def _draw_dom(self, r: SDLRenderer, f: Any, x: int, y: int, w: int, h: int) -> None:
        if not hasattr(self, "_dom_ref") or not self._dom_ref:
            r.draw_text(x, y, "No DOM loaded", f, "#888888")
            return
        lines = []
        self._flatten_dom(self._dom_ref, 0, lines)
        lh = 16
        start = self.scroll // lh
        for i, (indent, text, color) in enumerate(lines[start:]):
            ly = y + i * lh
            if ly > y + h:
                break
            r.draw_text(x + indent * 12, ly, text[:60], f, color)

    def _flatten_dom(self, node: Any, depth: int, out: list) -> None:
        if isinstance(node, Element):
            attrs = ""
            if node.attributes.get("id"):
                attrs += f' id="{node.attributes["id"]}"'
            if node.attributes.get("class"):
                attrs += f' class="{node.attributes["class"]}"'
            tag_str = f"<{node.tag}{attrs}>"
            out.append((depth, tag_str, "#569cd6"))
            for c in node.children:
                self._flatten_dom(c, depth + 1, out)
            out.append((depth, f"</{node.tag}>", "#569cd6"))
        elif isinstance(node, Text):
            text = node.text.strip()
            if text:
                out.append((depth, f'"{text[:40]}"', "#ce9178"))

    def _draw_console(self, r: SDLRenderer, f: Any, x: int, y: int, w: int, h: int) -> None:
        if not self.console_lines:
            r.draw_text(x, y, "Console is empty", f, "#888888")
            return
        lh = 16
        visible = h // lh
        start = max(0, len(self.console_lines) - visible)
        for i, (level, msg, ts) in enumerate(self.console_lines[start:]):
            ly = y + i * lh
            if ly > y + h:
                break
            color = "#cc6666" if level == "error" else "#d4d4a0" if level == "warn" else "#cccccc"
            r.draw_text(x, ly, f"[{ts}]", f, "#666666")
            r.draw_text(x + 70, ly, msg[:60], f, color)

    def _draw_network(self, r: SDLRenderer, f: Any, fb: Any, x: int, y: int, w: int, h: int) -> None:
        if not self.network_log:
            r.draw_text(x, y, "No network requests", f, "#888888")
            return
        r.draw_text(x, y, "Method", fb, "#888888")
        r.draw_text(x + 55, y, "Status", fb, "#888888")
        r.draw_text(x + 105, y, "Size", fb, "#888888")
        r.draw_text(x + 155, y, "URL", fb, "#888888")
        y += 18
        lh = 16
        for entry in self.network_log[-(h // lh):]:
            status = entry["status"]
            sc = "#4ec9b0" if 200 <= status < 300 else "#cc6666" if status >= 400 else "#cccccc"
            r.draw_text(x, y, entry["method"], f, "#9cdcfe")
            r.draw_text(x + 55, y, str(status), f, sc)
            size = entry["size"]
            size_str = f"{size // 1024}K" if size > 1024 else f"{size}B"
            r.draw_text(x + 105, y, size_str, f, "#888888")
            url = entry["url"]
            if len(url) > 50:
                url = "..." + url[-47:]
            r.draw_text(x + 155, y, url, f, "#cccccc")
            y += lh

    def set_dom(self, dom: Any) -> None:
        self._dom_ref = dom

    def handle_click(self, x: int, y: int, panel_x: int, panel_y: int) -> bool:
        if not self.visible:
            return False
        rel_x = x - panel_x
        rel_y = y - panel_y
        if rel_y < 24:
            tabs = [("dom", 0), ("console", 80), ("network", 160)]
            for tid, tx in tabs:
                if tx <= rel_x <= tx + 75:
                    self.active_tab = tid
                    self.scroll = 0
                    return True
        return True

    def handle_scroll(self, dy: int) -> None:
        if self.visible:
            self.scroll = max(0, self.scroll - dy * 16)

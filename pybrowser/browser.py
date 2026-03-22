"""Browser shell -- SDL2 window, tabs, event loop, chrome, page rendering."""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import sdl2

from .css_parser import CSSParser, sort_rules, style
from .html_parser import Element, HTMLParser, Text
from .js import JSRuntime, create_engine
from .layout import DocumentLayout, set_base_url, set_renderer
from .paint import DrawText, paint_tree
from .renderer import SDLRenderer
from .tab import Tab
from .url import Url

INITIAL_WIDTH, INITIAL_HEIGHT = 1200, 900
SCROLL_STEP = 60
CHROME_HEIGHT = 60
TAB_BAR_HEIGHT = 26
ADDR_BAR_Y = TAB_BAR_HEIGHT
SCROLLBAR_WIDTH = 8
BOOKMARKS_FILE = os.path.expanduser("~/.pybrowser/bookmarks.json")
HISTORY_FILE = os.path.expanduser("~/.pybrowser/history.json")

DEFAULT_STYLESHEET = """
head { display: none; } style { display: none; } script { display: none; }
meta { display: none; } link { display: none; } title { display: none; }
h1 { font-size: 32px; font-weight: bold; margin-top: 21px; margin-bottom: 21px; }
h2 { font-size: 24px; font-weight: bold; margin-top: 20px; margin-bottom: 20px; }
h3 { font-size: 19px; font-weight: bold; margin-top: 18px; margin-bottom: 18px; }
h4 { font-size: 16px; font-weight: bold; margin-top: 21px; margin-bottom: 21px; }
h5 { font-size: 13px; font-weight: bold; margin-top: 22px; margin-bottom: 22px; }
h6 { font-size: 11px; font-weight: bold; margin-top: 25px; margin-bottom: 25px; }
p { margin-top: 16px; margin-bottom: 16px; }
blockquote { margin-top: 16px; margin-bottom: 16px; margin-left: 40px; margin-right: 40px; }
pre { font-family: Courier; white-space: pre; margin-top: 16px; margin-bottom: 16px; }
ul { margin-top: 16px; margin-bottom: 16px; padding-left: 40px; }
ol { margin-top: 16px; margin-bottom: 16px; padding-left: 40px; }
li { margin-top: 4px; margin-bottom: 4px; }
b { font-weight: bold; } strong { font-weight: bold; }
i { font-style: italic; } em { font-style: italic; }
a { color: #0066cc; } code { font-family: Courier; }
small { font-size: 13px; } hr { margin-top: 8px; margin-bottom: 8px; }
"""


class Browser:
    def __init__(self, js_engine: str = "auto") -> None:
        self._js_engine_pref = js_engine
        self.width = INITIAL_WIDTH
        self.height = INITIAL_HEIGHT

        self.renderer = SDLRenderer(self.width, self.height, "Pybrowser")
        set_renderer(self.renderer)

        self.tabs: List[Tab] = []
        self._active_tab = 0
        self._visited_urls: set = set()
        self._zoom = 1.0

        self._address_text = ""
        self._address_focused = False
        self._address_cursor = 0

        self._find_active = False
        self._find_text = ""
        self._find_cursor = 0

        self._alert_text: Optional[str] = None
        self._dropdown_open: Optional[Element] = None
        self._dropdown_options: List[Element] = []
        self._dropdown_rect: tuple = (0, 0, 0, 0)
        self._dropdown_item_h = 24
        self._loading = False

        self._font = self.renderer.get_font(13, "normal", "roman", "Helvetica")
        self._font_bold = self.renderer.get_font(13, "bold", "roman", "Helvetica")

        self._bookmarks = self._load_bookmarks()
        self._history_log: List[dict] = self._load_history()

    @property
    def tab(self) -> Tab:
        if not self.tabs:
            self.tabs.append(Tab())
        return self.tabs[self._active_tab]

    # -- main event loop ----------------------------------------------------

    def run(self) -> None:
        running = True
        while running:
            for event in self.renderer.poll_events():
                t = event["type"]
                if t == "quit":
                    running = False
                elif t == "click":
                    self._handle_click(event["x"], event["y"])
                elif t == "scroll":
                    self._handle_scroll(event["y"])
                elif t == "keydown":
                    self._handle_keydown(event)
                elif t == "textinput":
                    self._handle_textinput(event["text"])
                elif t == "resize":
                    self.width, self.height = event["w"], event["h"]
                    self.renderer.width, self.renderer.height = self.width, self.height
                    if self.tab.document:
                        self._relayout()

            self._tick_timers()
            self._draw()
            sdl2.SDL_Delay(16)

        self._save_history()
        self.renderer.destroy()

    # -- loading / rendering ------------------------------------------------

    def load(self, url: str) -> None:
        tab = self.tab
        self._address_text = url
        self._address_focused = False
        self._loading = True
        self._draw()

        if url.startswith("pybrowser://"):
            self._load_internal(url)
            return

        tab.current_url = Url(url)
        tab.url = url
        self._visited_urls.add(url)
        self._history_log.append({"url": url, "time": time.strftime("%Y-%m-%d %H:%M")})
        set_base_url(tab.current_url)

        body, resp_headers = self._fetch_with_headers(url)
        tab.csp = self._parse_csp(resp_headers.get("content-security-policy", ""))
        tab.dom = HTMLParser(body).parse()
        tab.rules = self._collect_rules(tab.dom)
        style(tab.dom, tab.rules)
        self._apply_visited_colors(tab.dom)

        tab.body_bg = self._find_body_bg()
        tab.title = self._find_title(tab.dom) or url[:40]
        self.renderer.set_title("Pybrowser - " + tab.title)

        tab.js_runtime = JSRuntime(
            tab.dom,
            engine=create_engine(self._js_engine_pref),
            on_mutate=self._on_js_mutate,
            on_log=self._on_console_log,
            on_alert=self._on_alert,
            base_url=tab.current_url,
        )
        tab.js_runtime.run_scripts(tab.dom, tab.current_url)
        self._collect_timers()
        self._loading = False

        self.renderer.flush_text_cache()
        tab.scroll = 0
        self._relayout()

    def _load_internal(self, url: str) -> None:
        tab = self.tab
        tab.url = url
        tab.current_url = None
        if url == "pybrowser://history":
            html = self._build_history_page()
        elif url == "pybrowser://bookmarks":
            html = self._build_bookmarks_page()
        else:
            html = "<html><body><h1>Not Found</h1><p>Unknown internal page.</p></body></html>"
        tab.dom = HTMLParser(html).parse()
        tab.rules = sort_rules(CSSParser(DEFAULT_STYLESHEET).parse())
        style(tab.dom, tab.rules)
        tab.body_bg = "#ffffff"
        tab.title = url.split("://")[1].capitalize()
        tab.js_runtime = None
        self._loading = False
        tab.scroll = 0
        self._relayout()

    def _fetch(self, url: str) -> str:
        url_obj = Url(url)
        if url_obj.view_source:
            body = url_obj.fetch()
            return self._highlight_source(body)
        return url_obj.fetch()

    def _fetch_with_headers(self, url: str) -> tuple:
        url_obj = Url(url)
        if url_obj.view_source:
            body = url_obj.fetch()
            return self._highlight_source(body), {}
        status, headers, body = url_obj.request()
        if 300 <= status < 400 and "location" in headers:
            loc = headers["location"]
            if loc.startswith("/"):
                loc = url_obj.origin + loc
            return self._fetch_with_headers(loc)
        return body, headers

    @staticmethod
    def _parse_csp(header: str) -> dict:
        csp: dict = {}
        if not header:
            return csp
        for directive in header.split(";"):
            parts = directive.strip().split()
            if len(parts) >= 2:
                csp[parts[0]] = parts[1:]
        return csp

    @staticmethod
    def _highlight_source(body: str) -> str:
        esc = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        esc = re.sub(r"(&lt;/?)([\w-]+)", r'<span style="color:#2980b9">\1\2</span>', esc)
        esc = re.sub(r'([\w-]+)(=&quot;[^&]*&quot;)', r'<span style="color:#27ae60">\1</span><span style="color:#e67e22">\2</span>', esc)
        return f'<body style="background-color:#2d2d2d; color:#f8f8f2; font-family:Courier; padding:16px;"><pre>{esc}</pre></body>'

    def _collect_rules(self, dom: Element) -> list:
        CSSParser.viewport_width = self.width
        default_rules = CSSParser(DEFAULT_STYLESHEET).parse()
        page_rules: list = []
        css_urls: list = []
        for node in self._iter_elements(dom):
            if node.tag == "style":
                for child in node.children:
                    if isinstance(child, Text):
                        try: page_rules.extend(CSSParser(child.text).parse())
                        except Exception: pass
            if node.tag == "link" and node.attributes.get("rel") == "stylesheet":
                href = node.attributes.get("href", "")
                if href and self.tab.current_url:
                    css_urls.append(self.tab.current_url.resolve(href))
        if css_urls:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(self._fetch_css, u): u for u in css_urls}
                for f in as_completed(futures):
                    try: page_rules.extend(f.result())
                    except Exception: pass
        return sort_rules(default_rules + page_rules)

    @staticmethod
    def _fetch_css(url: str) -> list:
        return CSSParser(Url(url).fetch()).parse()

    def _iter_elements(self, node: object) -> List[Element]:
        result: List[Element] = []
        if isinstance(node, Element):
            result.append(node)
            for child in node.children:
                result.extend(self._iter_elements(child))
        return result

    def _find_body_bg(self) -> str:
        if not self.tab.dom:
            return "#ffffff"
        for n in self._iter_elements(self.tab.dom):
            if n.tag in ("body", "html"):
                bg = n.style.get("background-color")
                if bg and bg not in ("transparent", "none"):
                    return bg
        return "#ffffff"

    @staticmethod
    def _find_title(dom: Element) -> str:
        def find(node):
            if isinstance(node, Element) and node.tag == "title":
                for c in node.children:
                    if isinstance(c, Text):
                        return c.text.strip()
            if isinstance(node, Element):
                for c in node.children:
                    r = find(c)
                    if r: return r
            return ""
        return find(dom)

    def _relayout(self) -> None:
        tab = self.tab
        tab.document = DocumentLayout(tab.dom, self.width)
        tab.document.layout()
        tab.display_list = []
        paint_tree(tab.document, tab.display_list)
        tab.max_y = max((cmd.bottom for cmd in tab.display_list), default=0)
        self._clamp_scroll()

    # -- drawing ------------------------------------------------------------

    def _draw(self) -> None:
        tab = self.tab
        self.renderer.clear(tab.body_bg)

        content_top = CHROME_HEIGHT
        sdl2.SDL_RenderSetClipRect(
            self.renderer._renderer,
            sdl2.SDL_Rect(0, content_top, self.width, self.height - content_top),
        )
        for cmd in tab.display_list:
            if cmd.bottom < tab.scroll or cmd.top > tab.scroll + self.height:
                continue
            cmd.execute(tab.scroll - content_top, self.renderer)
        sdl2.SDL_RenderSetClipRect(self.renderer._renderer, None)

        self._draw_scrollbar()
        self._draw_find_highlights()
        self._draw_chrome()
        self._draw_dropdown()
        self._draw_find_bar()
        if self._loading:
            self.renderer.draw_text(self.width // 2 - 40, self.height // 2, "Loading...", self._font, "#888888")
        if self._alert_text is not None:
            self._draw_alert()
        self.renderer.present()

    def _draw_scrollbar(self) -> None:
        tab = self.tab
        view = self.height - CHROME_HEIGHT
        if tab.max_y <= view:
            return
        bar_h = max(20, int(view * view / tab.max_y))
        bar_y = CHROME_HEIGHT + int(tab.scroll / tab.max_y * view)
        self.renderer.draw_rect(self.width - SCROLLBAR_WIDTH, bar_y, SCROLLBAR_WIDTH, bar_h, "#888888")

    def _draw_chrome(self) -> None:
        r = self.renderer
        f = self._font

        r.draw_rect(0, 0, self.width, CHROME_HEIGHT, "#e0e0e0")
        r.draw_line(0, CHROME_HEIGHT, self.width, CHROME_HEIGHT, "#bbbbbb", 1)

        # -- tab bar --
        tx = 4
        for i, t in enumerate(self.tabs):
            tw = min(160, max(80, f.measure(t.title[:18]) + 20))
            active = i == self._active_tab
            bg = "#ffffff" if active else "#d0d0d0"
            r.draw_rect(tx, 2, tw, TAB_BAR_HEIGHT - 2, bg)
            r.draw_outline(tx, 2, tw, TAB_BAR_HEIGHT - 2, "#aaaaaa")
            label = t.title[:18] + ("..." if len(t.title) > 18 else "")
            r.draw_text(tx + 6, 6, label, f, "#333333")
            close_x = tx + tw - 16
            r.draw_text(close_x, 5, "x", f, "#999999")
            tx += tw + 2

        r.draw_rect(tx + 2, 4, 22, 18, "#d8d8d8")
        r.draw_text(tx + 7, 5, "+", f, "#666666")

        # -- address bar --
        ay = TAB_BAR_HEIGHT + 2
        btn_w, btn_h = 26, 22
        # Back button -- left arrow
        r.draw_rect(4, ay, btn_w, btn_h, "#d0d0d0")
        r.draw_outline(4, ay, btn_w, btn_h, "#aaaaaa")
        ax, amid = 17, ay + btn_h // 2
        r.draw_line(ax, amid, ax - 7, amid, "#555555", 2)
        r.draw_line(ax - 7, amid, ax - 3, amid - 4, "#555555", 2)
        r.draw_line(ax - 7, amid, ax - 3, amid + 4, "#555555", 2)

        # Forward button -- right arrow
        r.draw_rect(34, ay, btn_w, btn_h, "#d0d0d0")
        r.draw_outline(34, ay, btn_w, btn_h, "#aaaaaa")
        ax2 = 43
        r.draw_line(ax2, amid, ax2 + 7, amid, "#555555", 2)
        r.draw_line(ax2 + 7, amid, ax2 + 3, amid - 4, "#555555", 2)
        r.draw_line(ax2 + 7, amid, ax2 + 3, amid + 4, "#555555", 2)

        # Bookmark button -- star shape
        is_bookmarked = self.tab.url in self._bookmarks
        r.draw_rect(64, ay, btn_w, btn_h, "#d0d0d0")
        r.draw_outline(64, ay, btn_w, btn_h, "#aaaaaa")
        sx, sy = 77, ay + 5
        star_color = "#f1c40f" if is_bookmarked else "#aaaaaa"
        r.draw_line(sx, sy, sx - 4, sy + 12, star_color, 2)
        r.draw_line(sx, sy, sx + 4, sy + 12, star_color, 2)
        r.draw_line(sx - 6, sy + 5, sx + 6, sy + 5, star_color, 2)
        r.draw_line(sx - 6, sy + 5, sx + 3, sy + 12, star_color, 2)
        r.draw_line(sx + 6, sy + 5, sx - 3, sy + 12, star_color, 2)

        addr_x = 96
        addr_w = self.width - addr_x - 8
        border = "#4488ff" if self._address_focused else "#bbbbbb"
        r.draw_rect(addr_x, ay, addr_w, btn_h, "#ffffff")
        r.draw_outline(addr_x, ay, addr_w, btn_h, border, 1)

        is_secure = self.tab.url.startswith("https://")
        text_offset = addr_x + 6
        if is_secure:
            lx, ly = addr_x + 8, ay + 4
            r.draw_rect(lx, ly + 4, 8, 6, "#27ae60")
            r.draw_outline(lx + 1, ly, 6, 5, "#27ae60", 1)
            text_offset = addr_x + 20
        elif self.tab.url and not self.tab.url.startswith("pybrowser://"):
            r.draw_text(addr_x + 6, ay + 4, "!", f, "#e74c3c")
            text_offset = addr_x + 18

        r.draw_text(text_offset, ay + 4, self._address_text, f, "#333333")
        if self._address_focused:
            cx = addr_x + 6 + f.measure(self._address_text[:self._address_cursor])
            r.draw_line(cx, ay + 3, cx, ay + btn_h - 3, "#333333", 1)

    def _draw_find_bar(self) -> None:
        if not self._find_active:
            return
        r = self.renderer
        f = self._font
        bh = 28
        by = self.height - bh
        r.draw_rect(0, by, self.width, bh, "#f0f0f0")
        r.draw_line(0, by, self.width, by, "#cccccc", 1)
        r.draw_text(8, by + 6, "Find:", f, "#555555")
        r.draw_rect(50, by + 3, 250, 22, "#ffffff")
        r.draw_outline(50, by + 3, 250, 22, "#4488ff", 1)
        r.draw_text(56, by + 6, self._find_text, f, "#333333")
        cx = 56 + f.measure(self._find_text[:self._find_cursor])
        r.draw_line(cx, by + 5, cx, by + 22, "#333333", 1)
        count = len(self.tab.find_matches)
        idx = self.tab.find_index + 1 if count else 0
        r.draw_text(310, by + 6, f"{idx}/{count}", f, "#888888")

    def _draw_find_highlights(self) -> None:
        tab = self.tab
        if not self._find_active or not tab.find_matches:
            return
        for i, (cmd, start, end) in enumerate(tab.find_matches):
            if cmd.bottom < tab.scroll or cmd.top > tab.scroll + self.height:
                continue
            sy = cmd.top - tab.scroll + CHROME_HEIGHT
            sx = cmd.left + (cmd.font.measure(cmd.text[:start]) if cmd.font else 0)
            sw = cmd.font.measure(cmd.text[start:end]) if cmd.font else 0
            color = "#ffff00" if i != tab.find_index else "#ff9900"
            self.renderer.draw_rect(sx, sy, sw, cmd.bottom - cmd.top, color)

    def _draw_dropdown(self) -> None:
        if self._dropdown_open is None:
            return
        r = self.renderer
        dx, dy, dw, dh = self._dropdown_rect
        f = self._font
        ih = self._dropdown_item_h
        r.draw_rect(dx - 1, dy - 1, dw + 2, dh + 2, "#888888")
        r.draw_rect(dx, dy, dw, dh, "#ffffff")
        for i, opt in enumerate(self._dropdown_options):
            oy = dy + 2 + i * ih
            sel = "selected" in opt.attributes
            if sel:
                r.draw_rect(dx + 1, oy, dw - 2, ih, "#3498db")
            label = ""
            for c in opt.children:
                if isinstance(c, Text): label += c.text.strip()
            r.draw_text(dx + 8, oy + 4, label, f, "#ffffff" if sel else "#333333")

    def _draw_alert(self) -> None:
        r = self.renderer
        ow = min(400, self.width - 40)
        oh = 120
        ox = (self.width - ow) // 2
        oy = (self.height - oh) // 2
        r.draw_rect(ox, oy, ow, oh, "#ffffff")
        r.draw_outline(ox, oy, ow, oh, "#333333", 2)
        r.draw_text(ox + 20, oy + 20, (self._alert_text or "")[:60], self._font, "#333333")
        bx = ox + (ow - 60) // 2
        by = oy + oh - 40
        r.draw_rect(bx, by, 60, 28, "#4488ff")
        r.draw_text(bx + 18, by + 5, "OK", self._font, "#ffffff")

    def _clamp_scroll(self) -> None:
        tab = self.tab
        mx = max(0, tab.max_y - (self.height - CHROME_HEIGHT))
        tab.scroll = max(0, min(tab.scroll, mx))

    # -- navigation ---------------------------------------------------------

    def _navigate(self, url: str) -> None:
        tab = self.tab
        if tab.current_url:
            tab.history.append(tab.current_url.url)
        tab.forward_stack.clear()
        self.load(url)

    def _go_back(self) -> None:
        tab = self.tab
        if not tab.history:
            return
        if tab.current_url:
            tab.forward_stack.append(tab.current_url.url)
        self.load(tab.history.pop())

    def _go_forward(self) -> None:
        tab = self.tab
        if not tab.forward_stack:
            return
        if tab.current_url:
            tab.history.append(tab.current_url.url)
        self.load(tab.forward_stack.pop())

    # -- tab management -----------------------------------------------------

    def _new_tab(self, url: str = "") -> None:
        self.tabs.append(Tab())
        self._active_tab = len(self.tabs) - 1
        if url:
            self.load(url)
        else:
            self._address_text = ""
            self._address_focused = True
            self._address_cursor = 0
            self.tab.title = "New Tab"
            self.tab.body_bg = "#ffffff"
            self.tab.dom = HTMLParser("<html><body></body></html>").parse()
            self.tab.rules = sort_rules(CSSParser(DEFAULT_STYLESHEET).parse())
            style(self.tab.dom, self.tab.rules)
            self._relayout()

    def _close_tab(self, idx: int) -> None:
        if len(self.tabs) <= 1:
            return
        self.tabs.pop(idx)
        if self._active_tab >= len(self.tabs):
            self._active_tab = len(self.tabs) - 1
        self._address_text = self.tab.url
        self.renderer.set_title("Pybrowser - " + self.tab.title)

    def _switch_tab(self, idx: int) -> None:
        if 0 <= idx < len(self.tabs):
            self._active_tab = idx
            self._address_text = self.tab.url
            if self.tab.current_url:
                set_base_url(self.tab.current_url)
            self.renderer.set_title("Pybrowser - " + self.tab.title)

    # -- event handling -----------------------------------------------------

    def _handle_click(self, x: int, y: int) -> None:
        if self._alert_text is not None:
            self._alert_text = None
            return
        if self._dropdown_open is not None:
            self._handle_dropdown_click(x, y)
            return
        if y < TAB_BAR_HEIGHT:
            self._handle_tab_click(x)
            return
        if y < CHROME_HEIGHT:
            self._handle_chrome_click(x, y)
            return
        if self._find_active and y > self.height - 28:
            return

        self._address_focused = False
        doc_y = y - CHROME_HEIGHT + self.tab.scroll
        clicked_node = self._node_at(x, doc_y)
        old_focus = self.tab.focused_input
        self.tab.focused_input = None

        element = self._find_ancestor_element(clicked_node)
        if element and element.tag == "input":
            itype = element.attributes.get("type", "text")
            if itype in ("checkbox", "radio"):
                self._toggle_check(element)
                return
            elif itype == "submit":
                self._submit_form(element)
                return
            else:
                self._focus_input(element)
                return
        if element and element.tag == "textarea":
            self._focus_input(element)
            return
        if element and element.tag == "select":
            self._open_dropdown(element, x, y)
            return
        if element and element.tag == "button":
            form = self._find_ancestor(element, ("form",))
            if form:
                self._submit_form_el(form)
                return
            if self.tab.js_runtime:
                self.tab.js_runtime.dispatch_click(element)
            return
        if old_focus:
            self._unfocus(old_focus)
        if clicked_node and self.tab.js_runtime:
            if self.tab.js_runtime.dispatch_click(clicked_node):
                return
        href = self._link_at(x, doc_y)
        if href and not href.startswith("#") and not href.startswith("mailto:") and not href.startswith("javascript:"):
            resolved = self.tab.current_url.resolve(href) if self.tab.current_url else href
            self._navigate(resolved)

    def _handle_tab_click(self, x: int) -> None:
        tx = 4
        f = self._font
        for i, t in enumerate(self.tabs):
            tw = min(160, max(80, f.measure(t.title[:18]) + 20))
            if tx <= x < tx + tw:
                close_x = tx + tw - 16
                if x >= close_x:
                    self._close_tab(i)
                else:
                    self._switch_tab(i)
                return
            tx += tw + 2
        if tx + 2 <= x <= tx + 24:
            self._new_tab()

    def _handle_chrome_click(self, x: int, y: int) -> None:
        if x < 30:
            self._go_back()
        elif x < 60:
            self._go_forward()
        elif x < 90:
            self._toggle_bookmark()
        elif x >= 96:
            self._address_focused = True
            self._address_cursor = len(self._address_text)

    def _handle_scroll(self, y: int) -> None:
        self.tab.scroll -= y * SCROLL_STEP
        self._clamp_scroll()

    def _handle_keydown(self, event: dict) -> None:
        if self._alert_text is not None:
            self._alert_text = None
            return
        if self._dropdown_open is not None:
            self._dropdown_open = None
            self._dropdown_options = []
            return

        sym = event["sym"]
        mod = event["mod"]
        ctrl = mod & (sdl2.KMOD_CTRL | sdl2.KMOD_GUI)

        if ctrl and sym == sdl2.SDLK_t:
            self._new_tab()
            return
        if ctrl and sym == sdl2.SDLK_w:
            self._close_tab(self._active_tab)
            return
        if ctrl and sym == sdl2.SDLK_f:
            self._find_active = not self._find_active
            if self._find_active:
                self._find_text = ""
                self._find_cursor = 0
            return
        if ctrl and sym == sdl2.SDLK_d:
            self._toggle_bookmark()
            return
        if ctrl and sym == sdl2.SDLK_h:
            self._new_tab("pybrowser://history")
            return
        if ctrl and sym == sdl2.SDLK_EQUALS:
            self._zoom = min(self._zoom + 0.1, 3.0); self._on_js_mutate(); return
        if ctrl and sym == sdl2.SDLK_MINUS:
            self._zoom = max(self._zoom - 0.1, 0.3); self._on_js_mutate(); return
        if ctrl and sym == sdl2.SDLK_0:
            self._zoom = 1.0; self._on_js_mutate(); return

        if self._find_active:
            self._handle_find_key(sym)
            return
        if self._address_focused:
            self._handle_address_key(sym)
            return

        if not self.tab.focused_input:
            if sym == sdl2.SDLK_DOWN:
                self.tab.scroll += SCROLL_STEP; self._clamp_scroll()
            elif sym == sdl2.SDLK_UP:
                self.tab.scroll -= SCROLL_STEP; self._clamp_scroll()
            return

        node = self.tab.focused_input
        current = node.attributes.get("value", "")
        if sym == sdl2.SDLK_BACKSPACE:
            node.attributes["value"] = current[:-1]; self._on_js_mutate()
        elif sym == sdl2.SDLK_RETURN:
            form = self._find_ancestor(node, ("form",))
            if form:
                self._unfocus(node); self.tab.focused_input = None
                self._submit_form_el(form); return
            if self.tab.js_runtime:
                self.tab.js_runtime.dispatch_event(node, "change")
            self.tab.focused_input = None; node._focused = False; self._on_js_mutate()
        elif sym == sdl2.SDLK_ESCAPE:
            self._unfocus(node); self.tab.focused_input = None; node._focused = False; self._on_js_mutate()

    def _handle_textinput(self, text: str) -> None:
        if self._find_active:
            self._find_text = self._find_text[:self._find_cursor] + text + self._find_text[self._find_cursor:]
            self._find_cursor += len(text)
            self._update_find()
            return
        if self._address_focused:
            self._address_text = self._address_text[:self._address_cursor] + text + self._address_text[self._address_cursor:]
            self._address_cursor += len(text)
            return
        if self.tab.focused_input:
            node = self.tab.focused_input
            node.attributes["value"] = node.attributes.get("value", "") + text
            if self.tab.js_runtime:
                self.tab.js_runtime.dispatch_event(node, "input")
            self._on_js_mutate()

    def _handle_address_key(self, sym: int) -> None:
        if sym == sdl2.SDLK_RETURN:
            url = self._address_text.strip()
            if url:
                if "://" not in url and not url.startswith("pybrowser://"):
                    url = "https://" + url
                self._address_focused = False
                self._navigate(url)
        elif sym == sdl2.SDLK_BACKSPACE:
            if self._address_cursor > 0:
                self._address_text = self._address_text[:self._address_cursor - 1] + self._address_text[self._address_cursor:]
                self._address_cursor -= 1
        elif sym == sdl2.SDLK_ESCAPE:
            self._address_focused = False
        elif sym == sdl2.SDLK_LEFT:
            self._address_cursor = max(0, self._address_cursor - 1)
        elif sym == sdl2.SDLK_RIGHT:
            self._address_cursor = min(len(self._address_text), self._address_cursor + 1)

    # -- find in page -------------------------------------------------------

    def _handle_find_key(self, sym: int) -> None:
        if sym == sdl2.SDLK_RETURN:
            if self.tab.find_matches:
                self.tab.find_index = (self.tab.find_index + 1) % len(self.tab.find_matches)
                self._scroll_to_find_match()
        elif sym == sdl2.SDLK_ESCAPE:
            self._find_active = False
            self.tab.find_matches = []
        elif sym == sdl2.SDLK_BACKSPACE:
            if self._find_cursor > 0:
                self._find_text = self._find_text[:self._find_cursor - 1] + self._find_text[self._find_cursor:]
                self._find_cursor -= 1
                self._update_find()

    def _update_find(self) -> None:
        tab = self.tab
        tab.find_matches = []
        tab.find_index = 0
        needle = self._find_text.lower()
        if not needle:
            return
        for cmd in tab.display_list:
            if not isinstance(cmd, DrawText) or not cmd.text:
                continue
            text_lower = cmd.text.lower()
            start = 0
            while True:
                idx = text_lower.find(needle, start)
                if idx == -1:
                    break
                tab.find_matches.append((cmd, idx, idx + len(needle)))
                start = idx + 1
        if tab.find_matches:
            self._scroll_to_find_match()

    def _scroll_to_find_match(self) -> None:
        tab = self.tab
        if not tab.find_matches:
            return
        cmd, _, _ = tab.find_matches[tab.find_index]
        view = self.height - CHROME_HEIGHT
        if cmd.top < tab.scroll or cmd.bottom > tab.scroll + view:
            tab.scroll = max(0, cmd.top - view // 3)
            self._clamp_scroll()

    # -- hit testing --------------------------------------------------------

    def _find_ancestor(self, node, tags):
        while node:
            if isinstance(node, Element) and node.tag in tags: return node
            node = getattr(node, "parent", None)
        return None

    def _find_ancestor_element(self, node):
        while node:
            if isinstance(node, Element) and node.tag in ("input", "button", "textarea", "select", "a"): return node
            if isinstance(node, Element) and getattr(node, "_widget_type", None): return node
            node = getattr(node, "parent", None)
        return None

    def _link_at(self, x, doc_y):
        for cmd in self.tab.display_list:
            if cmd.bottom < self.tab.scroll or cmd.top > self.tab.scroll + self.height: continue
            if not (cmd.left <= x <= cmd.right and cmd.top <= doc_y <= cmd.bottom): continue
            node = getattr(cmd, "node", None)
            while node:
                if isinstance(node, Element) and node.tag == "a":
                    href = node.attributes.get("href", "")
                    if href: return href
                node = getattr(node, "parent", None)
        return None

    def _node_at(self, x, doc_y):
        for cmd in self.tab.display_list:
            if cmd.bottom < self.tab.scroll or cmd.top > self.tab.scroll + self.height: continue
            if cmd.left <= x <= cmd.right and cmd.top <= doc_y <= cmd.bottom:
                node = getattr(cmd, "node", None)
                if node is not None: return node
        return None

    # -- input / form handling ----------------------------------------------

    def _focus_input(self, node):
        tab = self.tab
        if tab.focused_input and tab.focused_input is not node:
            self._unfocus(tab.focused_input)
        tab.focused_input = node
        node._focused = True
        if tab.js_runtime: tab.js_runtime.dispatch_event(node, "focus")
        self._on_js_mutate()

    def _unfocus(self, node):
        node._focused = False
        if self.tab.js_runtime:
            self.tab.js_runtime.dispatch_event(node, "blur")
            self.tab.js_runtime.dispatch_event(node, "change")

    def _open_dropdown(self, node, click_x, click_y):
        options = [c for c in node.children if isinstance(c, Element) and c.tag == "option"]
        if not options: return
        self._dropdown_open = node
        self._dropdown_options = options
        sx, sy = self._find_element_screen_pos(node)
        dw = max(getattr(node, "_widget_width", 120), 120)
        dh = self._dropdown_item_h * len(options) + 4
        dy = sy + 26
        if dy + dh > self.height: dy = sy - dh
        self._dropdown_rect = (int(sx), int(dy), int(dw), int(dh))

    def _handle_dropdown_click(self, x, y):
        dx, dy, dw, dh = self._dropdown_rect
        if dx <= x <= dx + dw and dy <= y <= dy + dh:
            idx = (y - dy - 2) // self._dropdown_item_h
            if 0 <= idx < len(self._dropdown_options):
                for opt in self._dropdown_options: opt.attributes.pop("selected", None)
                self._dropdown_options[idx].attributes["selected"] = ""
                if self.tab.js_runtime: self.tab.js_runtime.dispatch_event(self._dropdown_open, "change")
                self._on_js_mutate()
        self._dropdown_open = None; self._dropdown_options = []

    def _find_element_screen_pos(self, target):
        for cmd in self.tab.display_list:
            if getattr(cmd, "node", None) is target:
                return cmd.left, cmd.top - self.tab.scroll + CHROME_HEIGHT
        return 0, CHROME_HEIGHT

    def _toggle_check(self, node):
        if node.attributes.get("type") == "checkbox":
            if "checked" in node.attributes: del node.attributes["checked"]
            else: node.attributes["checked"] = ""
        elif node.attributes.get("type") == "radio":
            name = node.attributes.get("name", "")
            if name:
                form = self._find_ancestor(node, ("form",)) or self.tab.dom
                for el in self._iter_elements(form):
                    if el.tag == "input" and el.attributes.get("type") == "radio" and el.attributes.get("name") == name:
                        el.attributes.pop("checked", None)
            node.attributes["checked"] = ""
        if self.tab.js_runtime:
            self.tab.js_runtime.dispatch_event(node, "click")
            self.tab.js_runtime.dispatch_event(node, "change")
        self._on_js_mutate()

    def _submit_form(self, el):
        form = self._find_ancestor(el, ("form",))
        if form: self._submit_form_el(form)
        elif self.tab.js_runtime: self.tab.js_runtime.dispatch_click(el)

    def _submit_form_el(self, form):
        if self.tab.js_runtime and self.tab.js_runtime.dispatch_event(form, "submit"): return
        action = form.attributes.get("action", "")
        method = form.attributes.get("method", "GET").upper()
        data = [(el.attributes["name"], el.attributes.get("value", ""))
                for el in self._iter_elements(form)
                if el.tag == "input" and el.attributes.get("name")
                and el.attributes.get("type", "text") in ("hidden", "text", "password", "search")]
        if not action: action = self.tab.current_url.url if self.tab.current_url else ""
        resolved = self.tab.current_url.resolve(action) if self.tab.current_url else action
        if method == "GET":
            from urllib.parse import urlencode
            self._navigate(resolved + ("&" if "?" in resolved else "?") + urlencode(data))
        else:
            self._navigate(resolved)

    # -- bookmarks ----------------------------------------------------------

    def _toggle_bookmark(self) -> None:
        url = self.tab.url
        if url in self._bookmarks:
            del self._bookmarks[url]
        else:
            self._bookmarks[url] = self.tab.title
        self._save_bookmarks()

    @staticmethod
    def _load_bookmarks() -> dict:
        try:
            with open(BOOKMARKS_FILE) as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return {}

    def _save_bookmarks(self) -> None:
        os.makedirs(os.path.dirname(BOOKMARKS_FILE), exist_ok=True)
        with open(BOOKMARKS_FILE, "w") as f: json.dump(self._bookmarks, f)

    def _build_bookmarks_page(self) -> str:
        items = "".join(f'<li><a href="{u}">{t}</a></li>' for u, t in self._bookmarks.items())
        return f'<html><body style="font-family:Helvetica; padding:20px;"><h1>Bookmarks</h1><ul>{items}</ul></body></html>'

    # -- history ------------------------------------------------------------

    @staticmethod
    def _load_history() -> list:
        try:
            with open(HISTORY_FILE) as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return []

    def _save_history(self) -> None:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f: json.dump(self._history_log[-500:], f)

    def _build_history_page(self) -> str:
        items = "".join(
            f'<li><a href="{h["url"]}">{h["url"]}</a> <small style="color:#999">{h["time"]}</small></li>'
            for h in reversed(self._history_log[-100:])
        )
        return f'<html><body style="font-family:Helvetica; padding:20px;"><h1>History</h1><ul>{items}</ul></body></html>'

    # -- timers / JS callbacks ----------------------------------------------

    def _collect_timers(self) -> None:
        if not self.tab.js_runtime: return
        now = time.monotonic()
        for kind, fn, ms, tid in self.tab.js_runtime.get_pending_timers():
            self.tab.timers.append((kind, fn, ms, now + ms / 1000.0))

    def _tick_timers(self) -> None:
        tab = self.tab
        if not tab.timers or not tab.js_runtime: return
        now = time.monotonic()
        still, fired = [], False
        for kind, fn, ms, fire_at in tab.timers:
            if now >= fire_at:
                self._fire_timer(fn); fired = True
                if kind == "interval": still.append((kind, fn, ms, now + ms / 1000.0))
            else:
                still.append((kind, fn, ms, fire_at))
        tab.timers = still
        if fired: self._collect_timers(); self._on_js_mutate()

    def _fire_timer(self, fn) -> None:
        rt = self.tab.js_runtime
        if not rt: return
        if not rt._is_native:
            try:
                from .js.interpreter import JSFunction, NativeFunction
                if isinstance(fn, (JSFunction, NativeFunction)):
                    rt.engine.interp._call(fn, [], rt.engine.interp.global_env)
            except Exception: pass

    def _on_alert(self, msg): self._alert_text = str(msg)

    def _on_js_mutate(self) -> None:
        tab = self.tab
        if tab.dom:
            style(tab.dom, tab.rules)
            self._apply_visited_colors(tab.dom)
            self._relayout()

    def _apply_visited_colors(self, node) -> None:
        if isinstance(node, Element) and node.tag == "a":
            href = node.attributes.get("href", "")
            resolved = self.tab.current_url.resolve(href) if self.tab.current_url and href else href
            if resolved in self._visited_urls: node.style["color"] = "#8e44ad"
        if isinstance(node, Element):
            for c in node.children: self._apply_visited_colors(c)

    @staticmethod
    def _on_console_log(*args): print("[console]", " ".join(str(a) for a in args))

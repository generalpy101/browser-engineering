"""Browser shell -- SDL2 window, event loop, chrome, page rendering."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import sdl2

from .css_parser import CSSParser, Rule, sort_rules, style
from .html_parser import Element, HTMLParser, Node, Text
from .js import JSRuntime, create_engine
from .layout import DocumentLayout, set_base_url, set_renderer
from .paint import DisplayCommand, paint_tree
from .renderer import SDLRenderer
from .url import Url

INITIAL_WIDTH, INITIAL_HEIGHT = 1200, 900
SCROLL_STEP = 60
CHROME_HEIGHT = 36
SCROLLBAR_WIDTH = 8

DEFAULT_STYLESHEET = """
head { display: none; }
style { display: none; }
script { display: none; }
meta { display: none; }
link { display: none; }
title { display: none; }

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

b { font-weight: bold; }
strong { font-weight: bold; }
i { font-style: italic; }
em { font-style: italic; }
a { color: blue; }
code { font-family: Courier; }
small { font-size: 13px; }
hr { margin-top: 8px; margin-bottom: 8px; }
"""


class Browser:
    def __init__(self, js_engine: str = "auto") -> None:
        self._js_engine_pref = js_engine
        self.width = INITIAL_WIDTH
        self.height = INITIAL_HEIGHT

        self.renderer = SDLRenderer(self.width, self.height, "Pybrowser")
        set_renderer(self.renderer)

        self.scroll = 0
        self.max_y = 0
        self.display_list: List[DisplayCommand] = []
        self.document: Optional[DocumentLayout] = None
        self.dom: Optional[Element] = None
        self.rules: List[Rule] = []
        self.current_url: Optional[Url] = None
        self.history: List[str] = []
        self.forward_stack: List[str] = []
        self._body_bg = "#ffffff"
        self.js_runtime: Optional[JSRuntime] = None
        self._focused_input: Optional[Element] = None
        self._zoom = 1.0

        self._address_text = ""
        self._address_focused = False
        self._address_cursor = 0

        self._chrome_font = self.renderer.get_font(14, "normal", "roman", "Helvetica")
        self._loading = False

        self._timers: list = []
        self._alert_text: Optional[str] = None

    # -- main event loop ----------------------------------------------------

    def run(self) -> None:
        running = True
        while running:
            for event in self.renderer.poll_events():
                etype = event["type"]
                if etype == "quit":
                    running = False
                elif etype == "click":
                    self._handle_click(event["x"], event["y"])
                elif etype == "motion":
                    pass
                elif etype == "scroll":
                    self._handle_scroll(event["y"])
                elif etype == "keydown":
                    self._handle_keydown(event)
                elif etype == "textinput":
                    self._handle_textinput(event["text"])
                elif etype == "resize":
                    self.width = event["w"]
                    self.height = event["h"]
                    self.renderer.width = self.width
                    self.renderer.height = self.height
                    if self.document:
                        self._relayout()

            self._tick_timers()
            self._draw()
            sdl2.SDL_Delay(16)

        self.renderer.destroy()

    # -- loading / rendering ------------------------------------------------

    def load(self, url: str) -> None:
        self._address_text = url
        self._address_focused = False
        self._loading = True
        self._draw()

        self.current_url = Url(url)
        set_base_url(self.current_url)
        body = self._fetch(url)
        self.dom = HTMLParser(body).parse()
        self.rules = self._collect_rules(self.dom)
        style(self.dom, self.rules)

        self._body_bg = self._find_body_bg()
        self.renderer.set_title("Pybrowser - " + url)

        self.js_runtime = JSRuntime(
            self.dom,
            engine=create_engine(self._js_engine_pref),
            on_mutate=self._on_js_mutate,
            on_log=self._on_console_log,
            on_alert=self._on_alert,
            base_url=self.current_url,
        )
        self.js_runtime.run_scripts(self.dom, self.current_url)
        self._collect_timers()
        self._loading = False

        self.renderer.flush_text_cache()
        self._relayout()

    def _fetch(self, url: str) -> str:
        url_obj = Url(url)
        if url_obj.view_source:
            body = url_obj.fetch()
            return "<pre>" + body.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
        return url_obj.fetch()

    def _collect_rules(self, dom: Element) -> List[Rule]:
        default_rules = CSSParser(DEFAULT_STYLESHEET).parse()
        page_rules: List[Rule] = []

        css_urls: List[str] = []
        for node in self._iter_elements(dom):
            if node.tag == "style":
                for child in node.children:
                    if isinstance(child, Text):
                        try:
                            page_rules.extend(CSSParser(child.text).parse())
                        except Exception:
                            pass
            if node.tag == "link" and node.attributes.get("rel") == "stylesheet":
                href = node.attributes.get("href", "")
                if href and self.current_url:
                    css_urls.append(self.current_url.resolve(href))

        if css_urls:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(self._fetch_css, u): u for u in css_urls}
                for future in as_completed(futures):
                    try:
                        page_rules.extend(future.result())
                    except Exception:
                        pass

        return sort_rules(default_rules + page_rules)

    @staticmethod
    def _fetch_css(url: str) -> List[Rule]:
        body = Url(url).fetch()
        return CSSParser(body).parse()

    def _iter_elements(self, node: object) -> List[Element]:
        result: List[Element] = []
        if isinstance(node, Element):
            result.append(node)
            for child in node.children:
                result.extend(self._iter_elements(child))
        return result

    def _find_body_bg(self) -> str:
        if not self.dom:
            return "#ffffff"
        for node in self._iter_elements(self.dom):
            if node.tag in ("body", "html"):
                bg = node.style.get("background-color")
                if bg and bg not in ("transparent", "none"):
                    return bg
        return "#ffffff"

    def _relayout(self) -> None:
        content_height = self.height - CHROME_HEIGHT
        self.document = DocumentLayout(self.dom, self.width)
        self.document.layout()

        self.display_list = []
        paint_tree(self.document, self.display_list)

        self.max_y = max((cmd.bottom for cmd in self.display_list), default=0)
        self._clamp_scroll()

    def _draw(self) -> None:
        self.renderer.clear(self._body_bg)

        content_top = CHROME_HEIGHT
        sdl2.SDL_RenderSetClipRect(
            self.renderer._renderer,
            sdl2.SDL_Rect(0, content_top, self.width, self.height - content_top),
        )

        for cmd in self.display_list:
            if cmd.bottom < self.scroll:
                continue
            if cmd.top > self.scroll + self.height:
                continue
            cmd.execute(self.scroll - content_top, self.renderer)

        sdl2.SDL_RenderSetClipRect(self.renderer._renderer, None)

        self._draw_scrollbar()
        self._draw_chrome()

        if self._loading:
            f = self.renderer.get_font(18, "normal", "roman", "Helvetica")
            self.renderer.draw_text(self.width // 2 - 40, self.height // 2, "Loading...", f, "#888888")

        self._draw_alert()
        self.renderer.present()

    def _draw_scrollbar(self) -> None:
        if self.max_y <= self.height - CHROME_HEIGHT:
            return
        view = self.height - CHROME_HEIGHT
        bar_h = max(20, int(view * view / self.max_y))
        bar_y = CHROME_HEIGHT + int(self.scroll / self.max_y * view)
        self.renderer.draw_rect(self.width - SCROLLBAR_WIDTH, bar_y,
                                SCROLLBAR_WIDTH, bar_h, "#888888")

    def _draw_chrome(self) -> None:
        r = self.renderer
        r.draw_rect(0, 0, self.width, CHROME_HEIGHT, "#e8e8e8")
        r.draw_line(0, CHROME_HEIGHT, self.width, CHROME_HEIGHT, "#cccccc", 1)

        f = self._chrome_font
        btn_w = 28
        btn_h = 24
        btn_y = (CHROME_HEIGHT - btn_h) // 2

        r.draw_rect(4, btn_y, btn_w, btn_h, "#d0d0d0")
        r.draw_outline(4, btn_y, btn_w, btn_h, "#aaaaaa")
        r.draw_text(10, btn_y + 3, "\u2190", f, "#333333")

        r.draw_rect(36, btn_y, btn_w, btn_h, "#d0d0d0")
        r.draw_outline(36, btn_y, btn_w, btn_h, "#aaaaaa")
        r.draw_text(42, btn_y + 3, "\u2192", f, "#333333")

        addr_x = 70
        addr_w = self.width - addr_x - 8
        addr_h = 24
        addr_y = (CHROME_HEIGHT - addr_h) // 2
        border = "#4488ff" if self._address_focused else "#bbbbbb"
        r.draw_rect(addr_x, addr_y, addr_w, addr_h, "#ffffff")
        r.draw_outline(addr_x, addr_y, addr_w, addr_h, border, 1)

        text = self._address_text
        r.draw_text(addr_x + 6, addr_y + 4, text, f, "#333333")

        if self._address_focused:
            cursor_x = addr_x + 6 + f.measure(text[:self._address_cursor])
            r.draw_line(cursor_x, addr_y + 3, cursor_x, addr_y + addr_h - 3, "#333333", 1)

    def _draw_alert(self) -> None:
        if self._alert_text is None:
            return
        r = self.renderer
        overlay_w = min(400, self.width - 40)
        overlay_h = 120
        ox = (self.width - overlay_w) // 2
        oy = (self.height - overlay_h) // 2

        r.draw_rect(0, 0, self.width, self.height, "#00000088")
        r.draw_rect(ox, oy, overlay_w, overlay_h, "#ffffff")
        r.draw_outline(ox, oy, overlay_w, overlay_h, "#333333", 2)

        f = self.renderer.get_font(15, "normal", "roman", "Helvetica")
        r.draw_text(ox + 20, oy + 20, self._alert_text[:60], f, "#333333")

        btn_w, btn_h = 60, 28
        bx = ox + (overlay_w - btn_w) // 2
        by = oy + overlay_h - btn_h - 15
        r.draw_rect(bx, by, btn_w, btn_h, "#4488ff")
        r.draw_text(bx + 18, by + 5, "OK", f, "#ffffff")

    # -- timers -------------------------------------------------------------

    def _collect_timers(self) -> None:
        if not self.js_runtime:
            return
        now = time.monotonic()
        for kind, fn, ms, tid in self.js_runtime.get_pending_timers():
            fire_at = now + ms / 1000.0
            self._timers.append((kind, fn, ms, fire_at))

    def _tick_timers(self) -> None:
        if not self._timers or not self.js_runtime:
            return
        now = time.monotonic()
        still_pending = []
        fired = False
        for kind, fn, ms, fire_at in self._timers:
            if now >= fire_at:
                self._fire_timer(fn)
                fired = True
                if kind == "interval":
                    still_pending.append((kind, fn, ms, now + ms / 1000.0))
            else:
                still_pending.append((kind, fn, ms, fire_at))
        self._timers = still_pending
        if fired:
            self._collect_timers()
            self._on_js_mutate()

    def _fire_timer(self, fn: object) -> None:
        if not self.js_runtime:
            return
        rt = self.js_runtime
        if rt._is_native:
            pass
        else:
            try:
                from .js.engine import ToyJSEngine
                from .js.interpreter import JSFunction, NativeFunction
                if isinstance(rt.engine, ToyJSEngine) and isinstance(fn, (JSFunction, NativeFunction)):
                    rt.engine.interp._call(fn, [], rt.engine.interp.global_env)
            except Exception:
                pass

    def _on_alert(self, msg: str) -> None:
        self._alert_text = str(msg)

    def _clamp_scroll(self) -> None:
        max_scroll = max(0, self.max_y - (self.height - CHROME_HEIGHT))
        self.scroll = max(0, min(self.scroll, max_scroll))

    # -- navigation ---------------------------------------------------------

    def _navigate(self, url: str) -> None:
        if self.current_url:
            self.history.append(self.current_url.url)
        self.forward_stack.clear()
        self.scroll = 0
        self.load(url)

    def _go_back(self) -> None:
        if not self.history:
            return
        if self.current_url:
            self.forward_stack.append(self.current_url.url)
        self.scroll = 0
        self.load(self.history.pop())

    def _go_forward(self) -> None:
        if not self.forward_stack:
            return
        if self.current_url:
            self.history.append(self.current_url.url)
        self.scroll = 0
        self.load(self.forward_stack.pop())

    # -- event handling -----------------------------------------------------

    def _handle_click(self, x: int, y: int) -> None:
        if self._alert_text is not None:
            self._alert_text = None
            return
        if y < CHROME_HEIGHT:
            self._handle_chrome_click(x, y)
            return

        self._address_focused = False
        doc_y = y - CHROME_HEIGHT + self.scroll
        clicked_node = self._node_at(x, doc_y)

        old_focus = self._focused_input
        self._focused_input = None

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

        if element and element.tag == "button":
            form = self._find_ancestor(element, ("form",))
            if form:
                self._submit_form_el(form)
                return
            if self.js_runtime:
                self.js_runtime.dispatch_click(element)
            return

        if old_focus:
            self._unfocus(old_focus)

        if clicked_node and self.js_runtime:
            if self.js_runtime.dispatch_click(clicked_node):
                return

        href = self._link_at(x, doc_y)
        if href is None:
            return
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            return
        resolved = self.current_url.resolve(href) if self.current_url else href
        self._navigate(resolved)

    def _handle_chrome_click(self, x: int, y: int) -> None:
        if x < 32:
            self._go_back()
        elif x < 64:
            self._go_forward()
        elif x >= 70:
            self._address_focused = True
            self._address_cursor = len(self._address_text)

    def _handle_scroll(self, y: int) -> None:
        self.scroll -= y * SCROLL_STEP
        self._clamp_scroll()

    def _handle_keydown(self, event: dict) -> None:
        if self._alert_text is not None:
            self._alert_text = None
            return
        sym = event["sym"]
        mod = event["mod"]
        name = event.get("name", "")

        ctrl = mod & (sdl2.KMOD_CTRL | sdl2.KMOD_GUI)

        if ctrl and sym == sdl2.SDLK_EQUALS:
            self._zoom = min(self._zoom + 0.1, 3.0)
            self._on_js_mutate()
            return
        if ctrl and sym == sdl2.SDLK_MINUS:
            self._zoom = max(self._zoom - 0.1, 0.3)
            self._on_js_mutate()
            return
        if ctrl and sym == sdl2.SDLK_0:
            self._zoom = 1.0
            self._on_js_mutate()
            return

        if self._address_focused:
            self._handle_address_key(sym)
            return

        if sym == sdl2.SDLK_TAB:
            return

        if not self._focused_input:
            if sym == sdl2.SDLK_DOWN:
                self.scroll += SCROLL_STEP
                self._clamp_scroll()
            elif sym == sdl2.SDLK_UP:
                self.scroll -= SCROLL_STEP
                self._clamp_scroll()
            return

        node = self._focused_input
        current = node.attributes.get("value", "")
        if sym == sdl2.SDLK_BACKSPACE:
            node.attributes["value"] = current[:-1]
            self._on_js_mutate()
        elif sym == sdl2.SDLK_RETURN:
            form = self._find_ancestor(node, ("form",))
            if form:
                self._unfocus(node)
                self._focused_input = None
                self._submit_form_el(form)
                return
            if self.js_runtime:
                self.js_runtime.dispatch_event(node, "change")
            self._focused_input = None
            node._focused = False
            self._on_js_mutate()
        elif sym == sdl2.SDLK_ESCAPE:
            self._unfocus(node)
            self._focused_input = None
            node._focused = False
            self._on_js_mutate()

    def _handle_textinput(self, text: str) -> None:
        if self._address_focused:
            self._address_text = (
                self._address_text[:self._address_cursor]
                + text
                + self._address_text[self._address_cursor:]
            )
            self._address_cursor += len(text)
            return

        if self._focused_input:
            node = self._focused_input
            current = node.attributes.get("value", "")
            node.attributes["value"] = current + text
            if self.js_runtime:
                self.js_runtime.dispatch_event(node, "input")
            self._on_js_mutate()

    def _handle_address_key(self, sym: int) -> None:
        if sym == sdl2.SDLK_RETURN:
            url = self._address_text.strip()
            if url:
                if "://" not in url:
                    url = "https://" + url
                self._address_focused = False
                self._navigate(url)
        elif sym == sdl2.SDLK_BACKSPACE:
            if self._address_cursor > 0:
                self._address_text = (
                    self._address_text[:self._address_cursor - 1]
                    + self._address_text[self._address_cursor:]
                )
                self._address_cursor -= 1
        elif sym == sdl2.SDLK_ESCAPE:
            self._address_focused = False
        elif sym == sdl2.SDLK_LEFT:
            self._address_cursor = max(0, self._address_cursor - 1)
        elif sym == sdl2.SDLK_RIGHT:
            self._address_cursor = min(len(self._address_text), self._address_cursor + 1)

    # -- hit testing --------------------------------------------------------

    def _find_ancestor(self, node: Optional[Node], tags: tuple) -> Optional[Element]:
        while node:
            if isinstance(node, Element) and node.tag in tags:
                return node
            node = getattr(node, "parent", None)
        return None

    def _find_ancestor_element(self, node: Optional[Node]) -> Optional[Element]:
        while node:
            if isinstance(node, Element) and node.tag in (
                "input", "button", "textarea", "select", "a",
            ):
                return node
            if isinstance(node, Element) and getattr(node, "_widget_type", None):
                return node
            node = getattr(node, "parent", None)
        return None

    def _link_at(self, x: float, doc_y: float) -> Optional[str]:
        for cmd in self.display_list:
            if cmd.bottom < self.scroll or cmd.top > self.scroll + (self.height - CHROME_HEIGHT):
                continue
            if not (cmd.left <= x <= cmd.right and cmd.top <= doc_y <= cmd.bottom):
                continue
            node = getattr(cmd, "node", None)
            if node is None:
                continue
            while node:
                if isinstance(node, Element) and node.tag == "a":
                    href = node.attributes.get("href", "")
                    if href:
                        return href
                node = getattr(node, "parent", None)
        return None

    def _node_at(self, x: float, doc_y: float) -> Optional[Node]:
        for cmd in self.display_list:
            if cmd.bottom < self.scroll or cmd.top > self.scroll + (self.height - CHROME_HEIGHT):
                continue
            if cmd.left <= x <= cmd.right and cmd.top <= doc_y <= cmd.bottom:
                node = getattr(cmd, "node", None)
                if node is not None:
                    return node
        return None

    # -- input / form handling ----------------------------------------------

    def _focus_input(self, node: Element) -> None:
        if self._focused_input and self._focused_input is not node:
            self._unfocus(self._focused_input)
        self._focused_input = node
        node._focused = True
        if self.js_runtime:
            self.js_runtime.dispatch_event(node, "focus")
        self._on_js_mutate()

    def _unfocus(self, node: Element) -> None:
        node._focused = False
        if self.js_runtime:
            self.js_runtime.dispatch_event(node, "blur")
            self.js_runtime.dispatch_event(node, "change")

    def _toggle_check(self, node: Element) -> None:
        if node.attributes.get("type") == "checkbox":
            if "checked" in node.attributes:
                del node.attributes["checked"]
            else:
                node.attributes["checked"] = ""
        elif node.attributes.get("type") == "radio":
            name = node.attributes.get("name", "")
            if name:
                form = self._find_ancestor(node, ("form",)) or self.dom
                for el in self._iter_elements(form):
                    if (el.tag == "input" and el.attributes.get("type") == "radio"
                            and el.attributes.get("name") == name):
                        el.attributes.pop("checked", None)
            node.attributes["checked"] = ""
        if self.js_runtime:
            self.js_runtime.dispatch_event(node, "click")
            self.js_runtime.dispatch_event(node, "change")
        self._on_js_mutate()

    def _submit_form(self, submit_el: Element) -> None:
        form = self._find_ancestor(submit_el, ("form",))
        if form:
            self._submit_form_el(form)
        elif self.js_runtime:
            self.js_runtime.dispatch_click(submit_el)

    def _submit_form_el(self, form: Element) -> None:
        if self.js_runtime:
            if self.js_runtime.dispatch_event(form, "submit"):
                return
        action = form.attributes.get("action", "")
        method = form.attributes.get("method", "GET").upper()
        data = self._collect_form_data(form)
        if not action:
            action = self.current_url.url if self.current_url else ""
        resolved = self.current_url.resolve(action) if self.current_url else action
        if method == "GET":
            from urllib.parse import urlencode
            qs = urlencode(data)
            sep = "&" if "?" in resolved else "?"
            self._navigate(resolved + sep + qs)
        else:
            self._navigate(resolved)

    def _collect_form_data(self, form: Element) -> list:
        pairs = []
        for el in self._iter_elements(form):
            if el.tag != "input" or not el.attributes.get("name"):
                continue
            name = el.attributes["name"]
            itype = el.attributes.get("type", "text")
            if itype in ("hidden", "text", "password", "search"):
                pairs.append((name, el.attributes.get("value", "")))
            elif itype in ("checkbox", "radio"):
                if "checked" in el.attributes:
                    pairs.append((name, el.attributes.get("value", "on")))
        return pairs

    # -- JS callbacks -------------------------------------------------------

    def _on_js_mutate(self) -> None:
        if self.dom:
            style(self.dom, self.rules)
            self._relayout()

    @staticmethod
    def _on_console_log(*args: str) -> None:
        print("[console]", " ".join(str(a) for a in args))

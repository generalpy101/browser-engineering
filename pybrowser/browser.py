import sys
import time
import tkinter
import tkinter.font
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from .url import Url
from .html_parser import HTMLParser, Element, Text, Node
from .css_parser import CSSParser, style, sort_rules, Rule
from .layout import DocumentLayout
from .paint import paint_tree, DrawText, DrawRect, DisplayCommand
from .js_runtime import JSRuntime
from .js_engine import create_engine

INITIAL_WIDTH, INITIAL_HEIGHT = 1200, 900
SCROLL_STEP = 100
SCROLLBAR_WIDTH = 10

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
        self.window = tkinter.Tk()
        self.window.title("Pybrowser")

        self.width = INITIAL_WIDTH
        self.height = INITIAL_HEIGHT

        # -- browser chrome (top bar) --------------------------------------
        chrome = tkinter.Frame(self.window, bg="#ececec", pady=4)
        chrome.pack(side="top", fill="x")

        self.back_btn = tkinter.Button(
            chrome, text="\u2190", command=self._go_back, width=3,
        )
        self.back_btn.pack(side="left", padx=(6, 2))

        self.forward_btn = tkinter.Button(
            chrome, text="\u2192", command=self._go_forward, width=3,
        )
        self.forward_btn.pack(side="left", padx=2)

        self.address_bar = tkinter.Entry(chrome, font=("Helvetica", 14))
        self.address_bar.pack(side="left", fill="x", expand=True, padx=6)
        self.address_bar.bind("<Return>", self._on_address_enter)

        # -- canvas ---------------------------------------------------------
        self.canvas = tkinter.Canvas(
            self.window, width=self.width, height=self.height, bg="white",
        )
        self.canvas.pack(fill="both", expand=True)

        # -- state ----------------------------------------------------------
        self.scroll = 0
        self.max_y = 0
        self.display_list: List[DisplayCommand] = []
        self.document: Optional[DocumentLayout] = None
        self.dom: Optional[Element] = None
        self.current_url: Optional[Url] = None
        self.history: List[str] = []
        self.forward_stack: List[str] = []
        self._body_bg = "white"
        self._last_hover_time = 0.0
        self._last_hover_result: Optional[str] = None
        self.js_runtime: Optional[JSRuntime] = None
        self._focused_input: Optional[Element] = None

        # -- bindings -------------------------------------------------------
        self.window.bind("<Down>", self._on_scroll_down)
        self.window.bind("<Up>", self._on_scroll_up)
        self.window.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_hover)
        self.window.bind("<Key>", self._on_key)
        self._bind_mouse_wheel()

    # -- loading / rendering ------------------------------------------------

    def load(self, url: str) -> None:
        self.address_bar.delete(0, tkinter.END)
        self.address_bar.insert(0, url)

        self.canvas.delete("all")
        self.canvas.create_text(
            self.width / 2, self.height / 2,
            text="Loading...", font=("Helvetica", 18), fill="gray",
        )
        self.window.update()

        self.current_url = Url(url)
        body = self._fetch(url)
        self.dom = HTMLParser(body).parse()
        self.rules = self._collect_rules(self.dom)
        style(self.dom, self.rules)

        self._body_bg = self._find_body_bg()
        self.canvas.configure(bg=self._body_bg)
        self.window.title("Pybrowser - " + url)

        self.js_runtime = JSRuntime(
            self.dom,
            engine=create_engine(self._js_engine_pref),
            on_mutate=self._on_js_mutate,
            on_log=self._on_console_log,
            base_url=self.current_url,
        )
        self.js_runtime.run_scripts(self.dom, self.current_url)

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
            return "white"
        for node in self._iter_elements(self.dom):
            if node.tag in ("body", "html"):
                bg = node.style.get("background-color")
                if bg and bg not in ("transparent", "none"):
                    return bg
        return "white"

    def _relayout(self) -> None:
        self.document = DocumentLayout(self.dom, self.width)
        self.document.layout()

        self.display_list = []
        paint_tree(self.document, self.display_list)

        self.max_y = max(
            (cmd.bottom for cmd in self.display_list), default=0
        )
        self._clamp_scroll()
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.bottom < self.scroll:
                continue
            if cmd.top > self.scroll + self.height:
                continue
            cmd.execute(self.scroll, self.canvas)
        self._draw_scrollbar()

    def _draw_scrollbar(self) -> None:
        if self.max_y <= self.height:
            return
        bar_height = max(20, self.height * self.height / self.max_y)
        bar_top = self.scroll / self.max_y * self.height
        x = self.width - SCROLLBAR_WIDTH
        self.canvas.create_rectangle(
            x, bar_top, x + SCROLLBAR_WIDTH, bar_top + bar_height,
            fill="#888888", outline="",
        )

    def _clamp_scroll(self) -> None:
        max_scroll = max(0, self.max_y - self.height)
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
        url = self.history.pop()
        self.scroll = 0
        self.load(url)

    def _go_forward(self) -> None:
        if not self.forward_stack:
            return
        if self.current_url:
            self.history.append(self.current_url.url)
        url = self.forward_stack.pop()
        self.scroll = 0
        self.load(url)

    def _on_address_enter(self, e: tkinter.Event) -> None:
        url = self.address_bar.get().strip()
        if not url:
            return
        if "://" not in url:
            url = "https://" + url
        self._navigate(url)

    # -- click / link handling ----------------------------------------------

    def _on_click(self, e: tkinter.Event) -> None:
        self.canvas.focus_set()
        doc_y = e.y + self.scroll
        clicked_node = self._node_at(e.x, doc_y)

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

        href = self._link_at(e.x, doc_y)
        if href is None:
            return
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            return
        resolved = self.current_url.resolve(href) if self.current_url else href
        self._navigate(resolved)

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
            if itype == "hidden" or itype == "text" or itype == "password" or itype == "search":
                pairs.append((name, el.attributes.get("value", "")))
            elif itype in ("checkbox", "radio"):
                if "checked" in el.attributes:
                    pairs.append((name, el.attributes.get("value", "on")))
            elif itype == "submit":
                pass
        return pairs

    def _on_key(self, e: tkinter.Event) -> None:
        if e.widget == self.address_bar:
            return
        if not self._focused_input:
            return

        node = self._focused_input
        current = node.attributes.get("value", "")

        if e.keysym == "BackSpace":
            node.attributes["value"] = current[:-1]
        elif e.keysym == "Return":
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
        elif e.keysym == "Tab":
            pass
        elif e.keysym == "Escape":
            self._unfocus(node)
            self._focused_input = None
            node._focused = False
        elif len(e.char) == 1 and e.char.isprintable():
            node.attributes["value"] = current + e.char
            if self.js_runtime:
                self.js_runtime.dispatch_event(node, "input")
        else:
            return
        self._on_js_mutate()

    def _on_hover(self, e: tkinter.Event) -> None:
        now = time.monotonic()
        if now - self._last_hover_time < 0.05:
            return
        self._last_hover_time = now
        doc_y = e.y + self.scroll
        node = self._node_at(e.x, doc_y)
        element = self._find_ancestor_element(node)
        is_clickable = element is not None or self._link_at(e.x, doc_y) is not None
        cursor = "hand2" if is_clickable else ""
        if cursor != self._last_hover_result:
            self._last_hover_result = cursor
            self.canvas.config(cursor=cursor)

    def _link_at(self, x: float, doc_y: float) -> Optional[str]:
        """Return the href of any <a> element at the given document coordinates."""
        for cmd in self.display_list:
            if cmd.bottom < self.scroll or cmd.top > self.scroll + self.height:
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
        """Return the DOM node at the given document coordinates."""
        for cmd in self.display_list:
            if cmd.bottom < self.scroll or cmd.top > self.scroll + self.height:
                continue
            if cmd.left <= x <= cmd.right and cmd.top <= doc_y <= cmd.bottom:
                node = getattr(cmd, "node", None)
                if node is not None:
                    return node
        return None

    def _on_js_mutate(self) -> None:
        """Called when JS modifies the DOM -- restyle and relayout."""
        if self.dom:
            style(self.dom, self.rules)
            self._relayout()

    @staticmethod
    def _on_console_log(*args: str) -> None:
        print("[console]", " ".join(str(a) for a in args))

    # -- scroll handlers ----------------------------------------------------

    def _on_scroll_down(self, e: tkinter.Event) -> None:
        self.scroll += SCROLL_STEP
        self._clamp_scroll()
        self._draw()

    def _on_scroll_up(self, e: tkinter.Event) -> None:
        self.scroll -= SCROLL_STEP
        self._clamp_scroll()
        self._draw()

    def _on_resize(self, e: tkinter.Event) -> None:
        if e.widget != self.canvas:
            return
        if e.width == self.width and e.height == self.height:
            return
        self.width = e.width
        self.height = e.height
        if self.document is not None:
            self._relayout()

    def _bind_mouse_wheel(self) -> None:
        ws = self.window.tk.call("tk", "windowingsystem")
        if ws in ("win32", "aqua"):
            self.window.bind("<MouseWheel>", self._on_mouse_wheel)
        elif ws == "x11":
            self.window.bind("<Button-4>", self._on_linux_scroll)
            self.window.bind("<Button-5>", self._on_linux_scroll)

    def _on_mouse_wheel(self, event: tkinter.Event) -> None:
        if event.widget == self.address_bar:
            return
        if sys.platform == "darwin":
            self.scroll -= event.delta * 5
        else:
            self.scroll -= int(event.delta / 120) * SCROLL_STEP
        self._clamp_scroll()
        self._draw()

    def _on_linux_scroll(self, event: tkinter.Event) -> None:
        if event.num == 4:
            self.scroll -= SCROLL_STEP
        elif event.num == 5:
            self.scroll += SCROLL_STEP
        self._clamp_scroll()
        self._draw()


if __name__ == "__main__":
    from .__main__ import main
    main()

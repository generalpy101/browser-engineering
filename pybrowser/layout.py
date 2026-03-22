from __future__ import annotations

import io
import tkinter
import tkinter.font
from typing import Any, Dict, List, Optional

from .html_parser import Element, Node, Text

BLOCK_ELEMENTS = frozenset([
    "html", "body", "article", "section", "nav", "aside", "header", "footer",
    "main", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "pre", "hr", "blockquote", "table", "tr", "td", "th", "thead", "tbody",
    "form", "fieldset", "dl", "dt", "dd", "figure", "figcaption", "details",
    "summary", "address",
])

_font_cache: dict = {}
_image_cache: Dict[str, Any] = {}
_base_url_ref: list = [None]


def set_base_url(url: Any) -> None:
    _base_url_ref[0] = url


def _load_image(src: str) -> Any:
    """Load an image from a URL and return a tkinter PhotoImage, or None."""
    if src in _image_cache:
        return _image_cache[src]
    try:
        from .url import Url
        base = _base_url_ref[0]
        resolved = base.resolve(src) if base else src
        data = Url(resolved).fetch_binary()
        from PIL import Image, ImageTk
        img = Image.open(io.BytesIO(data))
        tk_img = ImageTk.PhotoImage(img)
        _image_cache[src] = tk_img
        return tk_img
    except Exception:
        _image_cache[src] = None
        return None


def get_font(size: int, weight: str, style: str, family: str) -> tkinter.font.Font:
    key = (size, weight, style, family)
    if key not in _font_cache:
        _font_cache[key] = tkinter.font.Font(
            size=size, weight=weight, slant=style, family=family,
        )
    return _font_cache[key]


def _resolve_px(value: str, default: float = 0.0) -> float:
    if not value:
        return default
    value = value.strip()
    if value == "auto":
        return default
    if value.endswith("px"):
        value = value[:-2]
    try:
        return float(value)
    except ValueError:
        return default


def _normalize_weight(value: str) -> str:
    """Tkinter only accepts 'normal' or 'bold'."""
    if not value:
        return "normal"
    value = value.strip()
    if value in ("bold", "bolder"):
        return "bold"
    try:
        return "bold" if int(value) >= 600 else "normal"
    except ValueError:
        return "normal"


def _is_block_node(child: Node) -> bool:
    if isinstance(child, Text):
        return False
    if child.style.get("display") == "none":
        return False
    return child.tag in BLOCK_ELEMENTS


def layout_mode(node: Node) -> str:
    if isinstance(node, Text):
        return "inline"
    if node.style.get("display", "block") == "none":
        return "none"
    if any(_is_block_node(c) for c in node.children):
        return "block"
    elif node.children:
        return "inline"
    else:
        return "block"


class _AnonInlineWrapper:
    """Virtual node that groups consecutive inline children for layout."""

    def __init__(self, inline_children: List[Node], parent_element: Node) -> None:
        self.children = inline_children
        self.parent = parent_element
        self.style = dict(getattr(parent_element, "style", {}))
        self.tag = ""
        self.attributes = {}


# ---------------------------------------------------------------------------
# Position model
# ---------------------------------------------------------------------------
# x, y   = top-left corner of the BORDER BOX (after margins, before padding)
# width   = border-box width  (padding-left + content + padding-right)
# height  = border-box height (padding-top  + content + padding-bottom)
#
# Content area starts at (x + padding_left, y + padding_top).
# Background fills (x, y) -> (x+width, y+height).
# Next sibling placed at  y + height + collapsed-margin.
# ---------------------------------------------------------------------------


class DocumentLayout:
    def __init__(self, node: Node, width: int) -> None:
        self.node = node
        self.parent: Optional[DocumentLayout] = None
        self.children: List[BlockLayout] = []
        self.x = 0
        self.y = 0
        self.width = width
        self.height = 0
        self.padding_top = 0
        self.padding_bottom = 0
        self.padding_left = 0
        self.padding_right = 0
        self.margin_bottom = 0

    def layout(self) -> None:
        child = BlockLayout(self.node, self, None)
        self.children = [child]
        child.layout()
        self.height = child.y + child.height

    def paint(self) -> list:
        return []


class BlockLayout:
    def __init__(
        self,
        node: Node,
        parent: object,
        previous: Optional[BlockLayout],
    ) -> None:
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children: list = []
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

    def layout(self) -> None:
        self._compute_position()
        mode = layout_mode(self.node)

        if mode == "block":
            self._layout_block()
        else:
            self._layout_inline()

    def _compute_position(self) -> None:
        s = getattr(self.node, "style", {})

        self.margin_top = _resolve_px(s.get("margin-top", "0"))
        self.margin_bottom = _resolve_px(s.get("margin-bottom", "0"))
        self.margin_left = _resolve_px(s.get("margin-left", "0"))
        self.margin_right = _resolve_px(s.get("margin-right", "0"))

        self.padding_top = _resolve_px(s.get("padding-top", "0"))
        self.padding_bottom = _resolve_px(s.get("padding-bottom", "0"))
        self.padding_left = _resolve_px(s.get("padding-left", "0"))
        self.padding_right = _resolve_px(s.get("padding-right", "0"))

        parent_content_w = (
            self.parent.width - self.parent.padding_left - self.parent.padding_right
        )

        specified_width = s.get("width")
        if specified_width and specified_width != "auto":
            self.width = _resolve_px(specified_width) + self.padding_left + self.padding_right
        else:
            self.width = parent_content_w - self.margin_left - self.margin_right

        max_width = s.get("max-width")
        if max_width and max_width not in ("none", "auto", "0.0px"):
            mw = _resolve_px(max_width) + self.padding_left + self.padding_right
            if 0 < mw < self.width:
                self.width = mw

        ml_auto = s.get("margin-left") == "auto"
        mr_auto = s.get("margin-right") == "auto"
        if (ml_auto or mr_auto) and self.width < parent_content_w:
            extra = parent_content_w - self.width
            if ml_auto and mr_auto:
                self.margin_left = extra / 2
                self.margin_right = extra / 2
            elif ml_auto:
                self.margin_left = extra
            else:
                self.margin_right = extra

        self.x = self.parent.x + self.parent.padding_left + self.margin_left

        if self.previous:
            collapsed = max(self.margin_top, self.previous.margin_bottom)
            self.y = self.previous.y + self.previous.height + collapsed
        else:
            self.y = self.parent.y + self.parent.padding_top + self.margin_top

    def _layout_block(self) -> None:
        groups = _group_children(self.node)
        previous: Optional[BlockLayout] = None
        for group in groups:
            next_block = BlockLayout(group, self, previous)
            self.children.append(next_block)
            next_block.layout()
            previous = next_block

        if self.children:
            last = self.children[-1]
            self.height = last.y + last.height - self.y + self.padding_bottom
        else:
            self.height = self.padding_top + self.padding_bottom

    def _layout_inline(self) -> None:
        inline = InlineLayout(self.node, self)
        self.children = [inline]
        inline.layout()
        self.height = self.padding_top + inline.height + self.padding_bottom

    def paint(self) -> list:
        cmds = []
        bg = getattr(self.node, "style", {}).get("background-color")
        if bg and bg != "transparent":
            from .paint import DrawRect
            cmds.append(DrawRect(
                self.x, self.y,
                self.x + self.width, self.y + self.height,
                bg,
            ))
        return cmds


def _group_children(node: Node) -> list:
    """Group consecutive inline children into _AnonInlineWrapper nodes."""
    children = node.children
    has_block = any(_is_block_node(c) for c in children)
    if not has_block:
        return [c for c in children
                if not (isinstance(c, Element) and c.style.get("display") == "none")]

    groups: list = []
    inline_buf: List[Node] = []

    for child in children:
        if isinstance(child, Element) and child.style.get("display") == "none":
            continue
        if _is_block_node(child):
            if inline_buf:
                groups.append(_AnonInlineWrapper(inline_buf, node))
                inline_buf = []
            groups.append(child)
        else:
            inline_buf.append(child)

    if inline_buf:
        groups.append(_AnonInlineWrapper(inline_buf, node))

    return groups


class InlineLayout:
    """Lays out inline/text content within a block, wrapping words into lines."""

    def __init__(self, node: Node, parent: BlockLayout) -> None:
        self.node = node
        self.parent = parent
        self.children: List[LineLayout] = []
        self.x = parent.x + parent.padding_left
        self.y = parent.y + parent.padding_top
        self.width = parent.width - parent.padding_left - parent.padding_right
        self.height = 0

        self._cursor_x = self.x
        self._current_line: List[tuple] = []

    def layout(self) -> None:
        if isinstance(self.node, _AnonInlineWrapper):
            for child in self.node.children:
                self._walk(child)
        else:
            self._walk(self.node)
        self._flush_line()

        cy = self.y
        for line in self.children:
            line.x = self.x
            line.y = cy
            line.width = self.width
            line.layout()
            cy += line.height
        self.height = cy - self.y

    def _walk(self, node: Node) -> None:
        if isinstance(node, Text):
            self._layout_text(node)
        elif isinstance(node, Element):
            if node.style.get("display") == "none":
                return
            if node.tag == "br":
                self._flush_line()
            elif node.tag == "input":
                self._layout_input(node)
                return
            elif node.tag == "button":
                self._layout_button(node)
                return
            elif node.tag == "img":
                self._layout_image(node)
                return
            for child in node.children:
                self._walk(child)

    def _layout_text(self, node: Text) -> None:
        node_style = node.parent.style if hasattr(node.parent, "style") else {}

        weight = _normalize_weight(node_style.get("font-weight", "normal"))
        fstyle = node_style.get("font-style", "normal")
        family = node_style.get("font-family", "Times")
        size_str = node_style.get("font-size", "16px")
        color = node_style.get("color", "black")

        slant = "italic" if fstyle == "italic" else "roman"
        size = int(_resolve_px(size_str, 16))
        if size < 1:
            size = 1
        font = get_font(size, weight, slant, family)

        if node_style.get("white-space") == "pre":
            for line_text in node.text.split("\n"):
                for word in (line_text.split(" ") if line_text else [""]):
                    self._place_word(word, font, color, node)
                    self._cursor_x += font.measure(" ")
                self._flush_line()
            return

        for word in node.text.split():
            self._place_word(word, font, color, node)
            self._cursor_x += font.measure(" ")

    def _layout_input(self, node: Element) -> None:
        node_style = getattr(node, "style", {})
        size = int(_resolve_px(node_style.get("font-size", "16px"), 16))
        if size < 1:
            size = 1
        font = get_font(size, "normal", "roman", "Helvetica")
        input_type = node.attributes.get("type", "text")

        if input_type == "hidden":
            return
        if input_type == "submit":
            label = node.attributes.get("value", "Submit")
            self._place_widget(label, font, "#333", node, "submit")
        elif input_type == "checkbox":
            checked = "checked" in node.attributes
            label = "\u2611" if checked else "\u2610"
            self._place_widget(label, font, "#333", node, "checkbox")
        elif input_type == "radio":
            checked = "checked" in node.attributes
            label = "\u25c9" if checked else "\u25cb"
            self._place_widget(label, font, "#333", node, "radio")
        else:
            value = node.attributes.get("value", "")
            placeholder = node.attributes.get("placeholder", "")
            if input_type == "password" and value:
                display = "\u2022" * len(value)
            else:
                display = value or placeholder
            color = "#333" if value else "#999"
            char_width = int(node.attributes.get("size", "20"))
            node._input_char_width = char_width
            self._place_widget(display, font, color, node, "input")

    def _layout_button(self, node: Element) -> None:
        node_style = getattr(node, "style", {})
        size = int(_resolve_px(node_style.get("font-size", "16px"), 16))
        if size < 1:
            size = 1
        font = get_font(size, "normal", "roman", "Helvetica")
        label = ""
        for child in node.children:
            if isinstance(child, Text):
                label += child.text.strip()
        label = label or "Button"
        self._place_widget(label, font, "#333", node, "button")

    def _layout_image(self, node: Element) -> None:
        src = node.attributes.get("src", "")
        if not src:
            return
        tk_img = _load_image(src)
        if tk_img:
            w = tk_img.width()
            h = tk_img.height()
        else:
            w, h = 20, 20
        attr_w = node.attributes.get("width")
        attr_h = node.attributes.get("height")
        if attr_w:
            try:
                w = int(attr_w)
            except ValueError:
                pass
        if attr_h:
            try:
                h = int(attr_h)
            except ValueError:
                pass
        if tk_img and attr_w and not attr_h:
            h = int(tk_img.height() * w / max(tk_img.width(), 1))
        if tk_img and attr_h and not attr_w:
            w = int(tk_img.width() * h / max(tk_img.height(), 1))

        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        node._img = tk_img
        node._img_w = w
        node._img_h = h
        node._widget_type = "image"
        self._current_line.append((self._cursor_x, "", None, "", node))
        self._cursor_x += w

    def _place_widget(self, text: str, font: tkinter.font.Font,
                      color: str, node: Element, widget_type: str) -> None:
        if widget_type in ("checkbox", "radio"):
            w = font.measure(text) + 4
        elif widget_type == "input":
            char_w = getattr(node, "_input_char_width", 20)
            w = max(font.measure("m") * char_w, font.measure(text) + 16)
        else:
            w = max(font.measure(text) + 24, 60)
        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        self._current_line.append((self._cursor_x, text, font, color, node))
        node._widget_type = widget_type
        node._widget_width = w
        self._cursor_x += w + font.measure(" ")

    def _place_word(
        self, word: str, font: tkinter.font.Font, color: str, node: Node,
    ) -> None:
        w = font.measure(word)
        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        self._current_line.append((self._cursor_x, word, font, color, node))
        self._cursor_x += w

    def _flush_line(self) -> None:
        if not self._current_line:
            return
        line = LineLayout(self.node, self)
        for x, word, font, color, dom_node in self._current_line:
            line.children.append(TextLayout(word, x, font, color, line, dom_node))
        self.children.append(line)
        self._current_line = []
        self._cursor_x = self.x

    def paint(self) -> list:
        return []


class LineLayout:
    def __init__(self, node: Node, parent: InlineLayout) -> None:
        self.node = node
        self.parent = parent
        self.children: List[TextLayout] = []
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

    def layout(self) -> None:
        if not self.children:
            self.height = 0
            return

        font_children = [c for c in self.children if c.font]
        max_ascent = max((c.font.metrics("ascent") for c in font_children), default=0)
        max_descent = max((c.font.metrics("descent") for c in font_children), default=0)
        max_img_h = max((c.height for c in self.children if not c.font), default=0)
        text_height = int(1.25 * (max_ascent + max_descent)) if (max_ascent + max_descent) else 0
        self.height = max(text_height, max_img_h)

        baseline = self.y + int(1.25 * max_ascent) if max_ascent else self.y + self.height
        for child in self.children:
            if child.font:
                child.y = baseline - child.font.metrics("ascent")
            else:
                child.y = baseline - child.height

        text_align = getattr(self.node, "style", {}).get("text-align", "left")
        if text_align in ("center", "right", "justify") and self.children:
            last = self.children[-1]
            used = last.x + (last.font.measure(last.word) if last.font else last.width) - self.x
            gap = self.width - used
            if text_align == "center":
                offset = gap / 2
            elif text_align == "right":
                offset = gap
            else:
                offset = 0
            if offset > 0:
                for child in self.children:
                    child.x += offset

    def paint(self) -> list:
        return []


class TextLayout:
    def __init__(
        self,
        word: str,
        x: float,
        font: tkinter.font.Font,
        color: str,
        parent: LineLayout,
        dom_node: Node = None,
    ) -> None:
        self.node = dom_node if dom_node is not None else parent.node
        self.word = word
        self.parent = parent
        self.children: list = []
        self.x = x
        self.y = 0
        self.font = font
        self.color = color

        if getattr(self.node, "_widget_type", None) == "image":
            self.width = getattr(self.node, "_img_w", 20)
            self.height = getattr(self.node, "_img_h", 20)
        elif font:
            self.width = font.measure(word)
            self.height = font.metrics("linespace")
        else:
            self.width = 0
            self.height = 0

    def paint(self) -> list:
        from .paint import DrawImage, DrawOutline, DrawRect, DrawText
        cmds = []
        widget_type = getattr(self.node, "_widget_type", None)
        if widget_type == "image":
            tk_img = getattr(self.node, "_img", None)
            w = getattr(self.node, "_img_w", 20)
            h = getattr(self.node, "_img_h", 20)
            if tk_img:
                cmds.append(DrawImage(self.x, self.y, w, h, tk_img, self.node))
            else:
                cmds.append(DrawRect(self.x, self.y, self.x + w, self.y + h, "#ddd", self.node))
                cmds.append(DrawOutline(self.x, self.y, self.x + w, self.y + h, "#999", 1, self.node))
            return cmds
        if widget_type:
            w = getattr(self.node, "_widget_width", self.width)
            h = self.font.metrics("linespace") + 8
            y = self.y - 4
            n = self.node
            focused = getattr(n, "_focused", False)

            if widget_type in ("button", "submit"):
                cmds.append(DrawRect(self.x, y, self.x + w, y + h, "#e8e8e8", n))
                border = "#4488ff" if focused else "#aaa"
                cmds.append(DrawOutline(self.x, y, self.x + w, y + h, border, 1, n))
                cmds.append(DrawText(self.x + 8, self.y, self.word, self.font, "#333", n))
            elif widget_type in ("checkbox", "radio"):
                cmds.append(DrawText(self.x, self.y, self.word, self.font, "#333", n))
            else:
                cmds.append(DrawRect(self.x, y, self.x + w, y + h, "white", n))
                border = "#4488ff" if focused else "#bbb"
                bw = 2 if focused else 1
                cmds.append(DrawOutline(self.x, y, self.x + w, y + h, border, bw, n))
                cmds.append(DrawText(self.x + 6, self.y, self.word, self.font, self.color, n))
                if focused:
                    cursor_x = self.x + 6 + self.font.measure(self.word)
                    from .paint import DrawLine
                    cmds.append(DrawLine(cursor_x, self.y, cursor_x, self.y + self.font.metrics("linespace"), "#333", 1))
        else:
            cmds.append(DrawText(self.x, self.y, self.word, self.font, self.color, self.node))
        return cmds

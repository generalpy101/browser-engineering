from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from .html_parser import Element, Node, Text

BLOCK_ELEMENTS = frozenset([
    "html", "body", "article", "section", "nav", "aside", "header", "footer",
    "main", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "pre", "hr", "blockquote", "table", "tr", "td", "th", "thead", "tbody",
    "form", "fieldset", "dl", "dt", "dd", "figure", "figcaption", "details",
    "summary", "address",
])

_renderer_ref: list = [None]
_image_cache: Dict[str, Any] = {}
_base_url_ref: list = [None]


def set_renderer(renderer: Any) -> None:
    _renderer_ref[0] = renderer


def set_base_url(url: Any) -> None:
    _base_url_ref[0] = url


def _load_image(src: str) -> Any:
    """Load raw image bytes from a URL, or None."""
    if src in _image_cache:
        return _image_cache[src]
    try:
        from .url import Url
        base = _base_url_ref[0]
        resolved = base.resolve(src) if base else src
        data = Url(resolved).fetch_binary()
        _image_cache[src] = data
        return data
    except Exception:
        _image_cache[src] = None
        return None


def _image_dimensions(data: bytes) -> tuple:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return img.width, img.height
    except Exception:
        return 0, 0


def get_font(size: int, weight: str, style: str, family: str) -> Any:
    r = _renderer_ref[0]
    if r:
        return r.get_font(size, weight, style, family)
    raise RuntimeError("Renderer not initialized -- call set_renderer() before layout")


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
    display = node.style.get("display", "block")
    if display == "none":
        return "none"
    if display == "inline-block":
        return "inline"
    if display in ("flex", "grid", "inline-flex", "inline-grid"):
        return "block"
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

        node_style = getattr(self.node, "style", {})
        display = node_style.get("display", "")

        if isinstance(self.node, Element) and self.node.tag == "tr":
            self._layout_table_row()
        elif display in ("grid", "inline-grid"):
            self._layout_grid()
        elif display in ("flex", "inline-flex"):
            self._layout_flex()
        elif mode == "block":
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

    def _layout_grid(self) -> None:
        s = getattr(self.node, "style", {})
        gap_str = s.get("gap", s.get("grid-gap", "0"))
        gap = _resolve_px(gap_str)
        row_gap = _resolve_px(s.get("row-gap", gap_str))
        col_gap = _resolve_px(s.get("column-gap", gap_str))

        children = [c for c in self.node.children
                    if not (isinstance(c, Element) and c.style.get("display") == "none")
                    and not (isinstance(c, Text) and c.text.strip() == "")]
        if not children:
            self.height = self.padding_top + self.padding_bottom
            return

        content_w = self.width - self.padding_left - self.padding_right

        col_template = s.get("grid-template-columns", "")
        col_widths = self._parse_grid_template(col_template, content_w, col_gap, len(children))
        num_cols = len(col_widths)

        blocks = []
        for child in children:
            block = BlockLayout(child, self, None)
            blocks.append(block)

        rows: List[List] = []
        row: list = []
        for block in blocks:
            row.append(block)
            if len(row) >= num_cols:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        cy = self.y + self.padding_top
        for ri, row_blocks in enumerate(rows):
            row_h = 0
            for ci, block in enumerate(row_blocks):
                cx = self.x + self.padding_left + sum(col_widths[:ci]) + ci * col_gap
                block._compute_position()
                block.x = cx
                block.y = cy
                block.width = col_widths[ci] if ci < len(col_widths) else col_widths[-1]
                block.margin_top = 0
                block.margin_bottom = 0
                mode = layout_mode(block.node)
                node_style = getattr(block.node, "style", {})
                disp = node_style.get("display", "")
                if disp == "grid":
                    block._layout_grid()
                elif disp == "flex":
                    block._layout_flex()
                elif mode == "block":
                    block._layout_block()
                else:
                    block._layout_inline()
                if block.height > row_h:
                    row_h = block.height
                self.children.append(block)
            cy += row_h + (row_gap if ri < len(rows) - 1 else 0)

        self.height = cy - self.y + self.padding_bottom

    @staticmethod
    def _parse_grid_template(template: str, available: float, gap: float, num_items: int) -> list:
        if not template or template == "none":
            cols = max(1, min(num_items, 1))
            return [available]

        parts = template.split()
        widths = []
        fr_parts = []
        remaining = available - gap * max(0, len(parts) - 1)

        for part in parts:
            if part.endswith("fr"):
                try:
                    fr_parts.append(float(part[:-2]))
                except ValueError:
                    fr_parts.append(1)
                widths.append(None)
            elif part.endswith("px"):
                try:
                    w = float(part[:-2])
                except ValueError:
                    w = 0
                remaining -= w
                fr_parts.append(0)
                widths.append(w)
            elif part.endswith("%"):
                try:
                    w = float(part[:-1]) / 100 * available
                except ValueError:
                    w = 0
                remaining -= w
                fr_parts.append(0)
                widths.append(w)
            elif part == "auto":
                fr_parts.append(1)
                widths.append(None)
            elif part.startswith("minmax("):
                fr_parts.append(1)
                widths.append(None)
            elif part.startswith("repeat("):
                inner = part[7:].rstrip(")")
                count_str, col_def = inner.split(",", 1) if "," in inner else ("1", inner)
                try:
                    count = int(count_str.strip())
                except ValueError:
                    count = 1
                col_def = col_def.strip()
                for _ in range(count):
                    if col_def.endswith("fr"):
                        fr_parts.append(float(col_def[:-2]) if col_def[:-2] else 1)
                        widths.append(None)
                    else:
                        w = _resolve_px(col_def)
                        remaining -= w
                        fr_parts.append(0)
                        widths.append(w)
            else:
                try:
                    w = float(part)
                    remaining -= w
                    fr_parts.append(0)
                    widths.append(w)
                except ValueError:
                    fr_parts.append(1)
                    widths.append(None)

        total_fr = sum(fr_parts)
        if total_fr > 0 and remaining > 0:
            fr_unit = remaining / total_fr
        else:
            fr_unit = 0

        result = []
        for i, w in enumerate(widths):
            if w is None:
                result.append(max(0, fr_unit * fr_parts[i]))
            else:
                result.append(max(0, w))

        return result if result else [available]

    def _layout_flex(self) -> None:
        s = getattr(self.node, "style", {})
        direction = s.get("flex-direction", "row")
        justify = s.get("justify-content", "flex-start")
        align = s.get("align-items", "stretch")

        children = [c for c in self.node.children
                    if not (isinstance(c, Element) and c.style.get("display") == "none")
                    and not (isinstance(c, Text) and c.text.strip() == "")]

        flex_items = []
        for child in children:
            block = BlockLayout(child, self, None)
            block._compute_position()
            mode = layout_mode(child)
            if mode == "block":
                block._layout_block()
            else:
                block._layout_inline()
            flex_items.append(block)

        content_w = self.width - self.padding_left - self.padding_right
        content_h = self.height if self.height > 0 else 0

        if direction == "row":
            total_w = sum(b.width + b.margin_left + b.margin_right for b in flex_items)
            gap = max(0, content_w - total_w)

            if justify == "center":
                cx = self.x + self.padding_left + gap / 2
            elif justify == "flex-end":
                cx = self.x + self.padding_left + gap
            elif justify == "space-between" and len(flex_items) > 1:
                cx = self.x + self.padding_left
                gap = gap / (len(flex_items) - 1)
            elif justify == "space-around" and flex_items:
                per = gap / len(flex_items)
                cx = self.x + self.padding_left + per / 2
                gap = per
            else:
                cx = self.x + self.padding_left

            max_h = 0
            for i, block in enumerate(flex_items):
                block.x = cx + block.margin_left
                block.y = self.y + self.padding_top + block.margin_top
                cx += block.width + block.margin_left + block.margin_right
                if justify in ("space-between", "space-around") and i < len(flex_items) - 1:
                    cx += gap
                if block.height > max_h:
                    max_h = block.height
            self.height = max_h + self.padding_top + self.padding_bottom

            if align == "center":
                for block in flex_items:
                    block.y = self.y + self.padding_top + (max_h - block.height) / 2
            elif align == "flex-end":
                for block in flex_items:
                    block.y = self.y + self.padding_top + max_h - block.height
        else:
            cy = self.y + self.padding_top
            for block in flex_items:
                block.x = self.x + self.padding_left + block.margin_left
                block.y = cy + block.margin_top
                cy += block.height + block.margin_top + block.margin_bottom
            self.height = cy - self.y + self.padding_bottom

        self.children = flex_items

    def _layout_table_row(self) -> None:
        cells = [c for c in self.node.children
                 if isinstance(c, Element) and c.tag in ("td", "th")
                 and c.style.get("display") != "none"]
        if not cells:
            self.height = 0
            return
        num_cols = len(cells)
        col_w = self.width / max(num_cols, 1)
        max_h = 0
        for i, cell in enumerate(cells):
            child = BlockLayout(cell, self, None)
            child.x = self.x + self.padding_left + i * col_w
            child.y = self.y + self.padding_top
            child.width = col_w
            child.margin_top = 0
            child.margin_bottom = 0
            child.margin_left = 0
            child.margin_right = 0
            child.padding_top = _resolve_px(getattr(cell, "style", {}).get("padding-top", "4"))
            child.padding_bottom = _resolve_px(getattr(cell, "style", {}).get("padding-bottom", "4"))
            child.padding_left = _resolve_px(getattr(cell, "style", {}).get("padding-left", "4"))
            child.padding_right = _resolve_px(getattr(cell, "style", {}).get("padding-right", "4"))
            mode = layout_mode(cell)
            if mode == "block":
                child._layout_block()
            else:
                child._layout_inline()
            self.children.append(child)
            if child.height > max_h:
                max_h = child.height
        self.height = max_h + self.padding_top + self.padding_bottom

    def paint(self) -> list:
        from .paint import ClipStart, DrawBoxShadow, DrawLine, DrawRect, DrawRoundedRect
        cmds = []
        s = getattr(self.node, "style", {})

        shadow = s.get("box-shadow")
        if shadow and shadow != "none":
            parts = shadow.split()
            sh_color = "#00000033"
            sh_x = sh_y = 0
            sh_blur = 4
            for p in parts:
                from .css_parser import resolve_color
                c = resolve_color(p)
                if c:
                    sh_color = c
                elif p.endswith("px"):
                    v = int(float(p[:-2]))
                    if sh_x == 0 and sh_y == 0:
                        sh_x = v
                    elif sh_y == 0:
                        sh_y = v
                    else:
                        sh_blur = v
            cmds.append(DrawBoxShadow(
                self.x, self.y, self.x + self.width, self.y + self.height,
                sh_color, sh_blur, 0, sh_x, sh_y,
            ))

        bg = s.get("background-color")
        radius_str = s.get("border-radius", "0")
        radius = int(_resolve_px(radius_str))
        alpha = int(float(s.get("opacity", "1")) * 255)
        alpha = max(0, min(255, alpha))

        if bg and bg != "transparent":
            if radius > 0:
                cmds.append(DrawRoundedRect(
                    self.x, self.y, self.x + self.width, self.y + self.height,
                    bg, radius, alpha,
                ))
            else:
                cmds.append(DrawRect(
                    self.x, self.y, self.x + self.width, self.y + self.height, bg,
                ))

        overflow = s.get("overflow", "visible")
        if overflow == "hidden":
            cmds.append(ClipStart(self.x, self.y, self.width, self.height))
            self._overflow_clip = True

        if isinstance(self.node, Element) and self.node.tag == "hr":
            line_y = self.y + self.height / 2
            cmds.append(DrawLine(self.x, line_y, self.x + self.width, line_y, "#cccccc", 1))

        return cmds

    def paint_post(self) -> list:
        if getattr(self, "_overflow_clip", False):
            from .paint import ClipEnd
            return [ClipEnd()]
        return []


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
            elif node.tag == "canvas":
                self._layout_canvas(node)
                return
            elif node.tag == "textarea":
                self._layout_textarea(node)
                return
            elif node.tag == "select":
                self._layout_select(node)
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
            node._checked = "checked" in node.attributes
            self._place_widget("", font, "#333", node, "checkbox")
        elif input_type == "radio":
            node._checked = "checked" in node.attributes
            self._place_widget("", font, "#333", node, "radio")
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

    def _layout_textarea(self, node: Element) -> None:
        node_style = getattr(node, "style", {})
        size = int(_resolve_px(node_style.get("font-size", "16px"), 16))
        if size < 1:
            size = 1
        font = get_font(size, "normal", "roman", "Courier")
        cols = int(node.attributes.get("cols", "40"))
        rows = int(node.attributes.get("rows", "4"))
        value = node.attributes.get("value", "")
        if not value:
            for child in node.children:
                if isinstance(child, Text):
                    value += child.text
        node.attributes["value"] = value

        lines = value.split("\n")
        node._textarea_lines = lines
        display = lines[0][:cols] if lines else ""
        w = font.measure("m") * cols + 12
        h = font.metrics("linespace") * rows + 8
        node._widget_type = "textarea"
        node._widget_width = w
        node._textarea_height = h
        node._textarea_font = font
        node._textarea_cols = cols
        node._textarea_rows = rows
        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        self._current_line.append((self._cursor_x, display, font, "#333", node))
        self._cursor_x += w + font.measure(" ")

    def _layout_select(self, node: Element) -> None:
        node_style = getattr(node, "style", {})
        size = int(_resolve_px(node_style.get("font-size", "16px"), 16))
        if size < 1:
            size = 1
        font = get_font(size, "normal", "roman", "Helvetica")
        selected_text = ""
        for child in node.children:
            if isinstance(child, Element) and child.tag == "option":
                if "selected" in child.attributes or not selected_text:
                    for gc in child.children:
                        if isinstance(gc, Text):
                            selected_text = gc.text.strip()
        label = selected_text or "(select)"
        node._widget_type = "select"
        w = max(font.measure(label) + 30, 100)
        node._widget_width = w
        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        self._current_line.append((self._cursor_x, label, font, "#333", node))
        self._cursor_x += w + font.measure(" ")

    def _layout_canvas(self, node: Element) -> None:
        w = int(node.attributes.get("width", "300"))
        h = int(node.attributes.get("height", "150"))
        cid = getattr(node, "_canvas_id", None)
        if cid is None:
            from .canvas2d import create_canvas
            cid = create_canvas(w, h)
            node._canvas_id = cid
        node._widget_type = "canvas"
        node._canvas_w = w
        node._canvas_h = h
        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        self._current_line.append((self._cursor_x, "", None, "", node))
        self._cursor_x += w

    def _layout_image(self, node: Element) -> None:
        src = node.attributes.get("src", "")
        if not src:
            return
        img_data = _load_image(src)
        if img_data:
            iw, ih = _image_dimensions(img_data)
            w, h = (iw or 20), (ih or 20)
        else:
            w, h = 20, 20
        attr_w = node.attributes.get("width")
        attr_h = node.attributes.get("height")
        if attr_w:
            try: w = int(attr_w)
            except ValueError: pass
        if attr_h:
            try: h = int(attr_h)
            except ValueError: pass
        if img_data and attr_w and not attr_h and iw:
            h = int(ih * w / max(iw, 1))
        if img_data and attr_h and not attr_w and ih:
            w = int(iw * h / max(ih, 1))

        if self._cursor_x + w > self.x + self.width and self._current_line:
            self._flush_line()
        node._img = img_data
        node._img_w = w
        node._img_h = h
        node._widget_type = "image"
        self._current_line.append((self._cursor_x, "", None, "", node))
        self._cursor_x += w

    def _place_widget(self, text: str, font: Any,
                      color: str, node: Element, widget_type: str) -> None:
        if widget_type in ("checkbox", "radio"):
            w = 18
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
        self, word: str, font: Any, color: str, node: Node,
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
        font: Any,
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
        if widget_type == "canvas":
            cid = getattr(self.node, "_canvas_id", None)
            w = getattr(self.node, "_canvas_w", 300)
            h = getattr(self.node, "_canvas_h", 150)
            cmds.append(DrawRect(self.x, self.y, self.x + w, self.y + h, "#ffffff", self.node))
            cmds.append(DrawOutline(self.x, self.y, self.x + w, self.y + h, "#cccccc", 1, self.node))
            if cid:
                from .paint import DrawCanvas
                cmds.append(DrawCanvas(self.x, self.y, w, h, cid, self.node))
            return cmds
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
            elif widget_type == "checkbox":
                checked = getattr(n, "_checked", False)
                bx, by = self.x + 1, self.y + 2
                bs = 14
                cmds.append(DrawRect(bx, by, bx + bs, by + bs, "#ffffff", n))
                cmds.append(DrawOutline(bx, by, bx + bs, by + bs, "#666666", 1, n))
                if checked:
                    from .paint import DrawLine
                    cmds.append(DrawLine(bx + 3, by + 7, bx + 6, by + 11, "#333333", 2))
                    cmds.append(DrawLine(bx + 6, by + 11, bx + 11, by + 3, "#333333", 2))
            elif widget_type == "radio":
                checked = getattr(n, "_checked", False)
                bx, by = self.x + 1, self.y + 2
                bs = 14
                cmds.append(DrawRect(bx, by, bx + bs, by + bs, "#ffffff", n))
                cmds.append(DrawOutline(bx, by, bx + bs, by + bs, "#666666", 1, n))
                if checked:
                    cmds.append(DrawRect(bx + 3, by + 3, bx + bs - 3, by + bs - 3, "#333333", n))
            elif widget_type == "textarea":
                th = getattr(n, "_textarea_height", h)
                cmds.append(DrawRect(self.x, y, self.x + w, y + th, "#ffffff", n))
                border = "#4488ff" if focused else "#bbb"
                bw = 2 if focused else 1
                cmds.append(DrawOutline(self.x, y, self.x + w, y + th, border, bw, n))
                ta_font = getattr(n, "_textarea_font", self.font)
                ta_lines = getattr(n, "_textarea_lines", [self.word])
                ta_rows = getattr(n, "_textarea_rows", 4)
                if ta_font:
                    lh = ta_font.metrics("linespace")
                    for li, line_text in enumerate(ta_lines[:ta_rows]):
                        cmds.append(DrawText(self.x + 6, self.y + li * lh, line_text, ta_font, "#333", n))
                    if focused:
                        last_line = ta_lines[-1] if ta_lines else ""
                        last_idx = min(len(ta_lines) - 1, ta_rows - 1)
                        cursor_x = self.x + 6 + ta_font.measure(last_line)
                        cursor_y = self.y + last_idx * lh
                        from .paint import DrawLine
                        cmds.append(DrawLine(cursor_x, cursor_y, cursor_x, cursor_y + lh, "#333", 1))
            elif widget_type == "select":
                cmds.append(DrawRect(self.x, y, self.x + w, y + h, "#f8f8f8", n))
                cmds.append(DrawOutline(self.x, y, self.x + w, y + h, "#aaa", 1, n))
                if self.font and self.word:
                    cmds.append(DrawText(self.x + 6, self.y, self.word, self.font, "#333", n))
                arrow_x = self.x + w - 16
                arrow_y = y + h // 2
                from .paint import DrawLine
                cmds.append(DrawLine(arrow_x, arrow_y - 3, arrow_x + 5, arrow_y + 3, "#666", 1))
                cmds.append(DrawLine(arrow_x + 5, arrow_y + 3, arrow_x + 10, arrow_y - 3, "#666", 1))
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

        if not widget_type and self.font:
            link_el = self._find_link_ancestor()
            if link_el:
                text_dec = getattr(link_el, "style", {}).get("text-decoration", "underline")
                if text_dec != "none":
                    from .paint import DrawLine
                    underline_y = self.y + self.font.metrics("ascent") + 2
                    cmds.append(DrawLine(self.x, underline_y, self.x + self.width, underline_y, self.color, 1))

        return cmds

    def _find_link_ancestor(self) -> Optional[Element]:
        node = self.node
        while node:
            if isinstance(node, Element) and node.tag == "a":
                return node
            node = getattr(node, "parent", None)
        return None

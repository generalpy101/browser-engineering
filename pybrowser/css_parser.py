from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple, Union

from .html_parser import Element, Node, Text

INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "font-family": "Times",
    "color": "black",
    "text-align": "left",
    "line-height": "1.25",
    "white-space": "normal",
}

NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
    "cyan": "#00ffff", "magenta": "#ff00ff", "orange": "#ffa500",
    "purple": "#800080", "pink": "#ffc0cb", "brown": "#a52a2a",
    "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
    "navy": "#000080", "teal": "#008080", "maroon": "#800000",
    "olive": "#808000", "lime": "#00ff00", "aqua": "#00ffff",
    "fuchsia": "#ff00ff", "darkred": "#8b0000", "darkgreen": "#006400",
    "darkblue": "#00008b", "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9",
    "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3",
    "dimgray": "#696969", "dimgrey": "#696969",
    "indianred": "#cd5c5c", "coral": "#ff7f50", "tomato": "#ff6347",
    "gold": "#ffd700", "khaki": "#f0e68c", "plum": "#dda0dd",
    "violet": "#ee82ee", "orchid": "#da70d6", "tan": "#d2b48c",
    "chocolate": "#d2691e", "firebrick": "#b22222", "crimson": "#dc143c",
    "steelblue": "#4682b4", "royalblue": "#4169e1", "skyblue": "#87ceeb",
    "slategray": "#708090", "slategrey": "#708090",
    "linen": "#faf0e6", "seashell": "#fff5ee", "snow": "#fffafa",
    "ivory": "#fffff0", "honeydew": "#f0fff0", "lavender": "#e6e6fa",
    "whitesmoke": "#f5f5f5", "ghostwhite": "#f8f8ff",
    "aliceblue": "#f0f8ff", "beige": "#f5f5dc",
    "inherit": "inherit", "transparent": "transparent",
}


def resolve_color(value: str) -> Optional[str]:
    """Normalize a CSS color value into a form tkinter understands (#RRGGBB or named)."""
    if not value:
        return None
    value = value.strip().lower()
    if "!important" in value:
        value = value.replace("!important", "").strip()
    if value.startswith("var("):
        return None
    if value in ("transparent", "none", "initial", "unset", "currentcolor"):
        return None
    if value == "inherit":
        return None

    if value in NAMED_COLORS:
        resolved = NAMED_COLORS[value]
        return None if resolved == "transparent" else resolved

    if value.startswith("#"):
        hexval = value[1:]
        if len(hexval) == 3:
            return "#" + "".join(c * 2 for c in hexval)
        if len(hexval) == 6:
            return value
        if len(hexval) == 8:
            return "#" + hexval[:6]
        return None

    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        r, g, b = min(r, 255), min(g, 255), min(b, 255)
        return f"#{r:02x}{g:02x}{b:02x}"

    m = re.match(
        r"rgba?\(\s*([\d.]+)%\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%", value,
    )
    if m:
        r = min(int(float(m.group(1)) * 2.55), 255)
        g = min(int(float(m.group(2)) * 2.55), 255)
        b = min(int(float(m.group(3)) * 2.55), 255)
        return f"#{r:02x}{g:02x}{b:02x}"

    if value.isalpha() and len(value) < 25:
        return value
    return None


# ---------------------------------------------------------------------------
# Unit resolution
# ---------------------------------------------------------------------------

def _to_px(value: str, ref_px: float = 16.0) -> float:
    """Convert a CSS length value to pixels. ref_px is the reference size (em base)."""
    if not value:
        return 0.0
    value = value.strip()
    if value == "auto" or value == "none":
        return 0.0
    if value.endswith("px"):
        try:
            return float(value[:-2])
        except ValueError:
            return 0.0
    if value.endswith("rem"):
        try:
            return float(value[:-3]) * 16.0
        except ValueError:
            return 0.0
    if value.endswith("em"):
        try:
            return float(value[:-2]) * ref_px
        except ValueError:
            return 0.0
    if value.endswith("ex"):
        try:
            return float(value[:-2]) * ref_px * 0.5
        except ValueError:
            return 0.0
    if value.endswith("ch"):
        try:
            return float(value[:-2]) * ref_px * 0.6
        except ValueError:
            return 0.0
    if value.endswith("%"):
        try:
            return float(value[:-1]) / 100.0 * ref_px
        except ValueError:
            return 0.0
    if value.endswith("pt"):
        try:
            return float(value[:-2]) * 1.333
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _resolve_font_size(value: str, parent_size: float) -> float:
    """Resolve a font-size value to pixels."""
    absolutes = {
        "xx-small": 9, "x-small": 10, "small": 13, "medium": 16,
        "large": 18, "x-large": 24, "xx-large": 32,
        "smaller": parent_size * 0.8, "larger": parent_size * 1.2,
    }
    if value in absolutes:
        return absolutes[value]
    if value.endswith("%"):
        try:
            return float(value[:-1]) / 100.0 * parent_size
        except ValueError:
            return parent_size
    if value.endswith("em"):
        try:
            return float(value[:-2]) * parent_size
        except ValueError:
            return parent_size
    return _to_px(value, parent_size)


# ---------------------------------------------------------------------------
# Shorthand expansion
# ---------------------------------------------------------------------------

def _expand_shorthands(body: Dict[str, str]) -> Dict[str, str]:
    result = dict(body)

    if "margin" in result:
        _expand_box(result, "margin", result.pop("margin"))
    if "padding" in result:
        _expand_box(result, "padding", result.pop("padding"))

    if "background" in result:
        bg = result.pop("background")
        if "background-color" not in result:
            result["background-color"] = bg.split()[0] if bg else bg

    if "border" in result:
        _expand_border(result, result.pop("border"), "")
    for side in ("top", "right", "bottom", "left"):
        key = f"border-{side}"
        if key in result:
            _expand_border(result, result.pop(key), f"-{side}")

    if "font" in result:
        _expand_font(result, result.pop("font"))

    return result


def _expand_box(result: dict, prefix: str, value: str) -> None:
    parts = value.split()
    if len(parts) == 1:
        t = r = b = l = parts[0]
    elif len(parts) == 2:
        t, r = parts[0], parts[1]
        b, l = t, r
    elif len(parts) == 3:
        t, r, b = parts[0], parts[1], parts[2]
        l = r
    elif len(parts) >= 4:
        t, r, b, l = parts[0], parts[1], parts[2], parts[3]
    else:
        return
    result.setdefault(f"{prefix}-top", t)
    result.setdefault(f"{prefix}-right", r)
    result.setdefault(f"{prefix}-bottom", b)
    result.setdefault(f"{prefix}-left", l)


def _expand_border(result: dict, value: str, suffix: str) -> None:
    parts = value.split()
    for part in parts:
        c = resolve_color(part)
        if c:
            result.setdefault(f"border-color{suffix}", part)


def _expand_font(result: dict, value: str) -> None:
    parts = value.split()
    for part in parts:
        if part in ("italic", "oblique"):
            result.setdefault("font-style", part)
        elif part in ("bold", "bolder", "lighter") or part.isdigit():
            result.setdefault("font-weight", part)
        elif part.endswith("px") or part.endswith("em") or part.endswith("%") or part.endswith("pt"):
            result.setdefault("font-size", part)
        elif "," in part or part in ("serif", "sans-serif", "monospace"):
            result.setdefault("font-family", part)


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

class TagSelector:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    @property
    def specificity(self) -> Tuple[int, int, int]:
        return (0, 0, 1)

    def matches(self, node: Node) -> bool:
        return isinstance(node, Element) and self.tag == node.tag

    def __repr__(self) -> str:
        return f"TagSelector({self.tag})"


class ClassSelector:
    def __init__(self, cls: str) -> None:
        self.cls = cls

    @property
    def specificity(self) -> Tuple[int, int, int]:
        return (0, 1, 0)

    def matches(self, node: Node) -> bool:
        if not isinstance(node, Element):
            return False
        classes = node.attributes.get("class", "").split()
        return self.cls in classes

    def __repr__(self) -> str:
        return f"ClassSelector(.{self.cls})"


class IdSelector:
    def __init__(self, id_: str) -> None:
        self.id = id_

    @property
    def specificity(self) -> Tuple[int, int, int]:
        return (1, 0, 0)

    def matches(self, node: Node) -> bool:
        if not isinstance(node, Element):
            return False
        return self.id == node.attributes.get("id", "")

    def __repr__(self) -> str:
        return f"IdSelector(#{self.id})"


class DescendantSelector:
    def __init__(self, ancestor: "Selector", descendant: "Selector") -> None:
        self.ancestor = ancestor
        self.descendant = descendant

    @property
    def specificity(self) -> Tuple[int, int, int]:
        a = self.ancestor.specificity
        d = self.descendant.specificity
        return (a[0] + d[0], a[1] + d[1], a[2] + d[2])

    def matches(self, node: Node) -> bool:
        if not self.descendant.matches(node):
            return False
        parent = node.parent
        while parent:
            if self.ancestor.matches(parent):
                return True
            parent = parent.parent
        return False

    def __repr__(self) -> str:
        return f"DescendantSelector({self.ancestor} {self.descendant})"


Selector = Union[TagSelector, ClassSelector, IdSelector, DescendantSelector]
Rule = Tuple[Selector, Dict[str, str]]


# ---------------------------------------------------------------------------
# CSS Parser
# ---------------------------------------------------------------------------

class CSSParser:
    def __init__(self, s: str) -> None:
        self.s = s
        self.i = 0

    def parse(self) -> List[Rule]:
        rules: List[Rule] = []
        while self.i < len(self.s):
            self._skip_whitespace_and_comments()
            if self.i >= len(self.s):
                break
            if self.s[self.i] == "@":
                self._skip_at_rule()
                continue
            try:
                selectors = self._parse_selector_list()
                body = self._parse_body()
                body = _expand_shorthands(body)
                for sel in selectors:
                    rules.append((sel, body))
            except Exception:
                self._skip_to_next_rule()
        return rules

    def _skip_whitespace_and_comments(self) -> None:
        while self.i < len(self.s):
            if self.s[self.i].isspace():
                self.i += 1
            elif self.s[self.i : self.i + 2] == "/*":
                end = self.s.find("*/", self.i + 2)
                self.i = end + 2 if end != -1 else len(self.s)
            else:
                break

    def _skip_at_rule(self) -> None:
        if "{" in self.s[self.i :]:
            brace_pos = self.s.index("{", self.i)
            depth = 1
            self.i = brace_pos + 1
            while self.i < len(self.s) and depth > 0:
                if self.s[self.i] == "{":
                    depth += 1
                elif self.s[self.i] == "}":
                    depth -= 1
                self.i += 1
        else:
            semi = self.s.find(";", self.i)
            self.i = semi + 1 if semi != -1 else len(self.s)

    def _skip_to_next_rule(self) -> None:
        pos = self.s.find("}", self.i)
        if pos != -1:
            self.i = pos + 1
        else:
            self.i = len(self.s)

    def _parse_selector_list(self) -> List[Selector]:
        selectors = [self._parse_selector()]
        while self.i < len(self.s) and self.s[self.i] == ",":
            self.i += 1
            try:
                selectors.append(self._parse_selector())
            except Exception:
                break
        return selectors

    def _parse_selector(self) -> Selector:
        self._skip_whitespace_and_comments()
        result = self._parse_simple_selector()
        while self.i < len(self.s) and self.s[self.i] not in ("{", ","):
            self._skip_whitespace_and_comments()
            if self.i < len(self.s) and self.s[self.i] in ("{", ","):
                break
            if self.i >= len(self.s):
                break
            if self.s[self.i] in (">", "+", "~"):
                self.i += 1
                self._skip_whitespace_and_comments()
            inner = self._parse_simple_selector()
            result = DescendantSelector(result, inner)
        return result

    def _parse_simple_selector(self) -> Selector:
        self._skip_whitespace_and_comments()
        if self.i < len(self.s) and self.s[self.i] == ".":
            self.i += 1
            name = self._parse_word()
            return ClassSelector(name)
        elif self.i < len(self.s) and self.s[self.i] == "#":
            self.i += 1
            name = self._parse_word()
            return IdSelector(name)
        elif self.i < len(self.s) and self.s[self.i] == "*":
            self.i += 1
            return TagSelector("*")
        else:
            name = self._parse_word()
            sel = TagSelector(name.casefold())
            while self.i < len(self.s) and self.s[self.i] in (".", "#", ":"):
                if self.s[self.i] == ":":
                    self._skip_pseudo()
                elif self.s[self.i] == ".":
                    self.i += 1
                    cls = self._parse_word()
                    sel = DescendantSelector(sel, ClassSelector(cls))
                elif self.s[self.i] == "#":
                    self.i += 1
                    id_ = self._parse_word()
                    sel = DescendantSelector(sel, IdSelector(id_))
            return sel

    def _skip_pseudo(self) -> None:
        while self.i < len(self.s) and self.s[self.i] == ":":
            self.i += 1
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] in "-_"):
            self.i += 1
        if self.i < len(self.s) and self.s[self.i] == "(":
            depth = 1
            self.i += 1
            while self.i < len(self.s) and depth > 0:
                if self.s[self.i] == "(":
                    depth += 1
                elif self.s[self.i] == ")":
                    depth -= 1
                self.i += 1

    def _parse_word(self) -> str:
        start = self.i
        while self.i < len(self.s) and (
            self.s[self.i].isalnum() or self.s[self.i] in "-_"
        ):
            self.i += 1
        if self.i == start:
            raise Exception(f"Expected word at position {self.i}")
        return self.s[start : self.i]

    def _parse_body(self) -> Dict[str, str]:
        self._skip_whitespace_and_comments()
        if self.i < len(self.s) and self.s[self.i] == "{":
            self.i += 1
        pairs: Dict[str, str] = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            self._skip_whitespace_and_comments()
            if self.i >= len(self.s) or self.s[self.i] == "}":
                break
            try:
                prop, val = self._parse_pair()
                pairs[prop.casefold()] = val
            except Exception:
                self._skip_to_semicolon()
        if self.i < len(self.s):
            self.i += 1
        return pairs

    def _parse_pair(self) -> Tuple[str, str]:
        prop = self._parse_word()
        self._skip_whitespace_and_comments()
        if self.i < len(self.s) and self.s[self.i] == ":":
            self.i += 1
        self._skip_whitespace_and_comments()
        val = self._parse_value()
        self._skip_whitespace_and_comments()
        if self.i < len(self.s) and self.s[self.i] == ";":
            self.i += 1
        return prop, val

    def _parse_value(self) -> str:
        start = self.i
        while self.i < len(self.s) and self.s[self.i] not in (";", "}"):
            self.i += 1
        return self.s[start : self.i].strip()

    def _skip_to_semicolon(self) -> None:
        while self.i < len(self.s) and self.s[self.i] not in (";", "}"):
            self.i += 1
        if self.i < len(self.s) and self.s[self.i] == ";":
            self.i += 1


# ---------------------------------------------------------------------------
# TagSelector("*") matches everything
# ---------------------------------------------------------------------------

_original_tag_matches = TagSelector.matches

def _universal_matches(self: TagSelector, node: Node) -> bool:
    if self.tag == "*":
        return isinstance(node, Element)
    return _original_tag_matches(self, node)

TagSelector.matches = _universal_matches  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Style resolution
# ---------------------------------------------------------------------------

def style(node: Node, rules: List[Rule]) -> None:
    """Resolve CSS styles for every node. Converts relative units to px."""
    if isinstance(node, Text):
        node.style = {}
        _inherit(node)
        return

    node.style = {}

    for selector, body in rules:
        if not selector.matches(node):
            continue
        for prop, val in body.items():
            node.style[prop] = val

    if "style" in node.attributes:
        inline_pairs = CSSParser(
            "inline { " + node.attributes["style"] + " }"
        ).parse()
        for _, body in inline_pairs:
            for prop, val in body.items():
                node.style[prop] = val

    _inherit(node)
    _resolve_units(node)

    for child in node.children:
        style(child, rules)


def _inherit(node: Node) -> None:
    for prop, default in INHERITED_PROPERTIES.items():
        if prop in node.style:
            continue
        if node.parent and hasattr(node.parent, "style"):
            node.style[prop] = node.parent.style.get(prop, default)
        else:
            node.style[prop] = default


def _resolve_units(node: Node) -> None:
    """Convert em/% values to px in-place so layout only sees px values."""
    parent_font_px = 16.0
    if node.parent and hasattr(node.parent, "style"):
        parent_font_px = _to_px(node.parent.style.get("font-size", "16px"))

    raw_fs = node.style.get("font-size", "16px")
    font_px = _resolve_font_size(raw_fs, parent_font_px)
    node.style["font-size"] = f"{font_px:.1f}px"

    for prop in (
        "margin-top", "margin-right", "margin-bottom", "margin-left",
        "padding-top", "padding-right", "padding-bottom", "padding-left",
        "width", "max-width", "line-height",
    ):
        raw = node.style.get(prop)
        if raw and raw != "auto" and raw != "none":
            if prop == "line-height":
                try:
                    val = float(raw)
                    node.style[prop] = f"{val * font_px:.1f}px"
                    continue
                except ValueError:
                    pass
            px = _to_px(raw, font_px)
            node.style[prop] = f"{px:.1f}px"

    for prop in ("color", "background-color"):
        raw = node.style.get(prop)
        if raw:
            resolved = resolve_color(raw)
            if resolved:
                node.style[prop] = resolved
            else:
                node.style.pop(prop, None)


def cascade_sort_key(rule: Rule) -> Tuple[int, int, int]:
    selector, _ = rule
    return selector.specificity


def sort_rules(rules: List[Rule]) -> List[Rule]:
    return sorted(rules, key=cascade_sort_key)

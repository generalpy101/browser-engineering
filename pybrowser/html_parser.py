from __future__ import annotations
from typing import Dict, List, Optional, Union

Node = Union["Text", "Element"]

SELF_CLOSING_TAGS = frozenset([
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
])

HEAD_TAGS = frozenset([
    "base", "basefont", "bgsound", "link", "meta", "title", "style", "script",
    "noscript",
])

ENTITY_MAP = {
    "lt": "<",
    "gt": ">",
    "amp": "&",
    "quot": '"',
    "apos": "'",
    "nbsp": "\u00a0",
    "copy": "\u00a9",
    "mdash": "\u2014",
    "ndash": "\u2013",
    "laquo": "\u00ab",
    "raquo": "\u00bb",
    "hellip": "\u2026",
}


class Text:
    def __init__(self, text: str, parent: Element) -> None:
        self.text = text
        self.parent = parent
        self.children: List[Node] = []

    def __repr__(self) -> str:
        abbr = self.text[:40].replace("\n", "\\n")
        return f"Text({abbr!r})"


class Element:
    def __init__(
        self, tag: str, attributes: Dict[str, str], parent: Optional[Element]
    ) -> None:
        self.tag = tag
        self.attributes = attributes
        self.parent = parent
        self.children: List[Node] = []

    def __repr__(self) -> str:
        attrs = " ".join(f'{k}="{v}"' for k, v in self.attributes.items())
        if attrs:
            return f"<{self.tag} {attrs}>"
        return f"<{self.tag}>"


def print_tree(node: Node, indent: int = 0) -> None:
    print(" " * indent + repr(node))
    for child in node.children:
        print_tree(child, indent + 2)


class HTMLParser:
    def __init__(self, body: str) -> None:
        self.body = body
        self.unfinished: List[Element] = []

    def parse(self) -> Element:
        text = ""
        in_tag = False
        i = 0
        while i < len(self.body):
            c = self.body[i]
            if c == "<":
                in_tag = True
                if text:
                    self._add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self._add_tag(text)
                text = ""
            else:
                text += c
            i += 1

        if not in_tag and text:
            self._add_text(text)

        return self._finish()

    def _add_text(self, text: str) -> None:
        if text.isspace():
            return
        self._implicit_tags(None)
        text = _decode_entities(text)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def _add_tag(self, text: str) -> None:
        tag, attributes = _parse_tag(text)
        if not tag:
            return
        if tag.startswith("!"):
            return

        self._implicit_tags(tag)

        if tag.startswith("/"):
            tag_name = tag[1:]
            if len(self.unfinished) == 1:
                return
            node = self._pop_until(tag_name)
            if node is None:
                return
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def _pop_until(self, tag_name: str) -> Optional[Element]:
        if not any(n.tag == tag_name for n in self.unfinished):
            return None

        while self.unfinished:
            node = self.unfinished.pop()
            if node.tag == tag_name:
                return node
            if self.unfinished:
                self.unfinished[-1].children.append(node)
        return None

    def _implicit_tags(self, tag: Optional[str]) -> None:
        while True:
            open_tags = [n.tag for n in self.unfinished]

            if open_tags == [] and tag != "html":
                self._add_tag("html")
            elif open_tags == ["html"] and tag not in ("head", "body", "/html"):
                if tag in HEAD_TAGS:
                    self._add_tag("head")
                else:
                    self._add_tag("body")
            elif (
                open_tags == ["html", "head"]
                and tag not in ("/head",)
                and tag not in HEAD_TAGS
            ):
                self._add_tag("/head")
            else:
                break

    def _finish(self) -> Element:
        if not self.unfinished:
            self._add_tag("html")
            self._add_tag("body")

        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)

        return self.unfinished.pop()


def _parse_tag(text: str) -> tuple:
    parts = text.split(None, 1)
    if not parts:
        return ("", {})
    tag = parts[0].casefold()
    attributes = {}
    if len(parts) > 1:
        attributes = _parse_attributes(parts[1])
    return tag, attributes


def _parse_attributes(text: str) -> Dict[str, str]:
    attributes: Dict[str, str] = {}
    i = 0
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break

        if text[i] == "/" and i + 1 >= len(text):
            break

        key_start = i
        while i < len(text) and text[i] not in ("=", " ", "\t", "\n", "/"):
            i += 1
        key = text[key_start:i].casefold()

        if not key:
            i += 1
            continue

        while i < len(text) and text[i].isspace():
            i += 1

        if i < len(text) and text[i] == "=":
            i += 1
            while i < len(text) and text[i].isspace():
                i += 1

            if i < len(text) and text[i] in ('"', "'"):
                quote = text[i]
                i += 1
                val_start = i
                while i < len(text) and text[i] != quote:
                    i += 1
                attributes[key] = text[val_start:i]
                i += 1
            else:
                val_start = i
                while i < len(text) and not text[i].isspace():
                    i += 1
                attributes[key] = text[val_start:i]
        else:
            attributes[key] = ""

    return attributes


def _decode_entities(text: str) -> str:
    result = []
    i = 0
    while i < len(text):
        if text[i] == "&":
            end = text.find(";", i + 1)
            if end != -1 and end - i < 10:
                entity_name = text[i + 1 : end]
                if entity_name.startswith("#x"):
                    try:
                        result.append(chr(int(entity_name[2:], 16)))
                        i = end + 1
                        continue
                    except ValueError:
                        pass
                elif entity_name.startswith("#"):
                    try:
                        result.append(chr(int(entity_name[1:])))
                        i = end + 1
                        continue
                    except ValueError:
                        pass
                elif entity_name in ENTITY_MAP:
                    result.append(ENTITY_MAP[entity_name])
                    i = end + 1
                    continue
        result.append(text[i])
        i += 1
    return "".join(result)

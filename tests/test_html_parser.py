from pybrowser.html_parser import Element, HTMLParser, Text


def parse(html):
    return HTMLParser(html).parse()


def text_of(node):
    if isinstance(node, Text):
        return node.text
    return "".join(text_of(c) for c in node.children)


def find_tag(node, tag):
    if isinstance(node, Element) and node.tag == tag:
        return node
    if isinstance(node, Element):
        for c in node.children:
            r = find_tag(c, tag)
            if r:
                return r
    return None


class TestBasicParsing:
    def test_simple_paragraph(self):
        dom = parse("<p>Hello</p>")
        p = find_tag(dom, "p")
        assert p is not None
        assert text_of(p) == "Hello"

    def test_nested_tags(self):
        dom = parse("<p>A <b>bold</b> word</p>")
        b = find_tag(dom, "b")
        assert b is not None
        assert text_of(b) == "bold"

    def test_self_closing_tags(self):
        dom = parse("<p>Line1<br>Line2</p>")
        p = find_tag(dom, "p")
        assert any(isinstance(c, Element) and c.tag == "br" for c in p.children)

    def test_attributes(self):
        dom = parse('<a href="https://example.com" class="link">Click</a>')
        a = find_tag(dom, "a")
        assert a.attributes["href"] == "https://example.com"
        assert a.attributes["class"] == "link"


class TestImplicitTags:
    def test_implicit_html_body(self):
        dom = parse("<p>Hi</p>")
        assert dom.tag == "html"
        body = find_tag(dom, "body")
        assert body is not None

    def test_implicit_head(self):
        dom = parse("<title>Test</title><p>Body</p>")
        head = find_tag(dom, "head")
        assert head is not None
        assert find_tag(head, "title") is not None


class TestEntityDecoding:
    def test_named_entities(self):
        dom = parse("<p>&amp; &lt; &gt;</p>")
        assert "& < >" in text_of(find_tag(dom, "p"))

    def test_numeric_entity(self):
        dom = parse("<p>&#65;</p>")
        assert "A" in text_of(find_tag(dom, "p"))

    def test_hex_entity(self):
        dom = parse("<p>&#x41;</p>")
        assert "A" in text_of(find_tag(dom, "p"))

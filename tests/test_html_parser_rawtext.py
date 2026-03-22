"""Test that <script> and <style> content is treated as raw text."""
from pybrowser.html_parser import Element, HTMLParser, Text


def find_tag(node, tag):
    if isinstance(node, Element) and node.tag == tag:
        return node
    if isinstance(node, Element):
        for c in node.children:
            r = find_tag(c, tag)
            if r: return r
    return None


def text_of(node):
    for c in node.children:
        if isinstance(c, Text):
            return c.text
    return ""


class TestScriptRawText:
    def test_script_preserves_lt_operator(self):
        dom = HTMLParser('<script>if (a < b) { x(); }</script>').parse()
        script = find_tag(dom, "script")
        assert script is not None
        content = text_of(script)
        assert "a < b" in content

    def test_script_preserves_angle_brackets(self):
        dom = HTMLParser('<script>var x = 1 < 2 && 3 > 1;</script>').parse()
        script = find_tag(dom, "script")
        content = text_of(script)
        assert "1 < 2" in content
        assert "3 > 1" in content

    def test_script_stops_at_closing_tag(self):
        dom = HTMLParser('<script>var x = 1;</script><p>after</p>').parse()
        script = find_tag(dom, "script")
        p = find_tag(dom, "p")
        assert text_of(script) == "var x = 1;"
        assert p is not None

    def test_style_preserves_content(self):
        dom = HTMLParser('<style>.foo > .bar { color: red; }</style>').parse()
        s = find_tag(dom, "style")
        content = text_of(s)
        assert ".foo > .bar" in content

    def test_multiple_scripts(self):
        dom = HTMLParser('<script>a();</script><script>b();</script>').parse()
        scripts = []
        def find_all(node):
            if isinstance(node, Element) and node.tag == "script":
                scripts.append(node)
            if isinstance(node, Element):
                for c in node.children: find_all(c)
        find_all(dom)
        assert len(scripts) == 2
        assert text_of(scripts[0]) == "a();"
        assert text_of(scripts[1]) == "b();"

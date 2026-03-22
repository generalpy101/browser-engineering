"""Test browser-level features: bookmarks, history, internal pages."""
import json
import os
import tempfile

from pybrowser.css_parser import CSSParser, sort_rules, style
from pybrowser.html_parser import Element, HTMLParser, Text


class TestBookmarks:
    def test_toggle_bookmark(self):
        bookmarks = {}
        url = "https://example.com"
        title = "Example"
        if url in bookmarks:
            del bookmarks[url]
        else:
            bookmarks[url] = title
        assert url in bookmarks
        assert bookmarks[url] == "Example"

        if url in bookmarks:
            del bookmarks[url]
        assert url not in bookmarks

    def test_bookmark_persistence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"https://a.com": "A"}, f)
            path = f.name
        try:
            with open(path) as f:
                data = json.load(f)
            assert data == {"https://a.com": "A"}
        finally:
            os.unlink(path)


class TestHistory:
    def test_history_log(self):
        history = []
        history.append({"url": "https://a.com", "time": "2026-01-01 12:00"})
        history.append({"url": "https://b.com", "time": "2026-01-01 12:01"})
        assert len(history) == 2
        assert history[-1]["url"] == "https://b.com"

    def test_history_limit(self):
        history = [{"url": f"https://{i}.com", "time": "now"} for i in range(600)]
        trimmed = history[-500:]
        assert len(trimmed) == 500


class TestInternalPages:
    def test_history_page_html(self):
        log = [
            {"url": "https://example.com", "time": "2026-03-22 12:00"},
            {"url": "https://test.com", "time": "2026-03-22 12:01"},
        ]
        items = "".join(
            f'<li><a href="{h["url"]}">{h["url"]}</a> <small>{h["time"]}</small></li>'
            for h in reversed(log)
        )
        html = f'<html><body><h1>History</h1><ul>{items}</ul></body></html>'
        dom = HTMLParser(html).parse()
        assert dom is not None

        def find(node, tag):
            if isinstance(node, Element) and node.tag == tag: return node
            if isinstance(node, Element):
                for c in node.children:
                    r = find(c, tag)
                    if r: return r
            return None

        h1 = find(dom, "h1")
        assert h1 is not None

    def test_bookmarks_page_html(self):
        bookmarks = {"https://a.com": "Site A", "https://b.com": "Site B"}
        items = "".join(f'<li><a href="{u}">{t}</a></li>' for u, t in bookmarks.items())
        html = f'<html><body><h1>Bookmarks</h1><ul>{items}</ul></body></html>'
        dom = HTMLParser(html).parse()

        links = []
        def find_links(node):
            if isinstance(node, Element) and node.tag == "a":
                links.append(node.attributes.get("href", ""))
            if isinstance(node, Element):
                for c in node.children: find_links(c)
        find_links(dom)
        assert "https://a.com" in links
        assert "https://b.com" in links


class TestTitleExtraction:
    def test_finds_title(self):
        dom = HTMLParser("<html><head><title>My Page</title></head><body></body></html>").parse()

        def find_title(node):
            if isinstance(node, Element) and node.tag == "title":
                for c in node.children:
                    if isinstance(c, Text): return c.text.strip()
            if isinstance(node, Element):
                for c in node.children:
                    r = find_title(c)
                    if r: return r
            return ""
        assert find_title(dom) == "My Page"

    def test_no_title(self):
        dom = HTMLParser("<html><body><p>No title</p></body></html>").parse()

        def find_title(node):
            if isinstance(node, Element) and node.tag == "title":
                for c in node.children:
                    if isinstance(c, Text): return c.text.strip()
            if isinstance(node, Element):
                for c in node.children:
                    r = find_title(c)
                    if r: return r
            return ""
        assert find_title(dom) == ""

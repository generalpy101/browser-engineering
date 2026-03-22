"""Test Tab state management."""
from pybrowser.tab import Tab


class TestTab:
    def test_default_state(self):
        t = Tab()
        assert t.url == ""
        assert t.title == "New Tab"
        assert t.scroll == 0
        assert t.display_list == []
        assert t.dom is None
        assert t.history == []
        assert t.forward_stack == []

    def test_with_url(self):
        t = Tab("https://example.com")
        assert t.url == "https://example.com"

    def test_find_state(self):
        t = Tab()
        assert t.find_text == ""
        assert t.find_matches == []
        assert t.find_index == 0

    def test_independent_state(self):
        t1 = Tab("https://a.com")
        t2 = Tab("https://b.com")
        t1.scroll = 100
        t2.scroll = 200
        assert t1.scroll == 100
        assert t2.scroll == 200
        t1.history.append("x")
        assert t2.history == []

from pybrowser.url import Url


class TestUrlParsing:
    def test_http(self):
        u = Url("http://example.com/path")
        assert u.protocol == "http"
        assert u.hostname == "example.com"
        assert u.path == "/path"
        assert u.port == 80

    def test_https_default_port(self):
        u = Url("https://example.com/")
        assert u.port == 443

    def test_custom_port(self):
        u = Url("http://localhost:8080/index.html")
        assert u.hostname == "localhost"
        assert u.port == 8080
        assert u.path == "/index.html"

    def test_no_path(self):
        u = Url("https://example.com")
        assert u.path == "/"

    def test_view_source(self):
        u = Url("view-source:https://example.com/")
        assert u.view_source is True
        assert u.protocol == "https"
        assert u.hostname == "example.com"


class TestUrlResolve:
    def setup_method(self):
        self.base = Url("https://example.com/dir/page.html")

    def test_absolute(self):
        assert self.base.resolve("https://other.com/x") == "https://other.com/x"

    def test_protocol_relative(self):
        assert self.base.resolve("//cdn.example.com/s.js") == "https://cdn.example.com/s.js"

    def test_path_absolute(self):
        assert self.base.resolve("/about.html") == "https://example.com/about.html"

    def test_relative(self):
        assert self.base.resolve("other.html") == "https://example.com/dir/other.html"

    def test_fragment(self):
        result = self.base.resolve("#section")
        assert "#section" in result

    def test_origin_no_default_port(self):
        u = Url("https://example.com/")
        assert u.origin == "https://example.com"

    def test_origin_custom_port(self):
        u = Url("http://localhost:3000/")
        assert u.origin == "http://localhost:3000"

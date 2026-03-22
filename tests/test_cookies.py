from pybrowser.url import CookieJar


class TestCookieJar:
    def setup_method(self):
        self.jar = CookieJar()
        self.jar._cookies = {}

    def test_set_and_get(self):
        self.jar.set_from_header("example.com", "session=abc123; Path=/")
        header = self.jar.get_header("example.com")
        assert "session=abc123" in header

    def test_multiple_cookies(self):
        self.jar.set_from_header("example.com", "a=1; Path=/")
        self.jar.set_from_header("example.com", "b=2; Path=/")
        header = self.jar.get_header("example.com")
        assert "a=1" in header
        assert "b=2" in header

    def test_path_matching(self):
        self.jar.set_from_header("example.com", "x=1; Path=/admin")
        assert self.jar.get_header("example.com", "/admin/page") != ""
        assert self.jar.get_header("example.com", "/public") == ""

    def test_get_all(self):
        self.jar.set_from_header("example.com", "k1=v1")
        self.jar.set_from_header("example.com", "k2=v2")
        all_cookies = self.jar.get_all("example.com")
        assert all_cookies == {"k1": "v1", "k2": "v2"}

    def test_clear_domain(self):
        self.jar.set_from_header("example.com", "x=1")
        self.jar.set_from_header("other.com", "y=2")
        self.jar._cookies.pop("example.com", None)
        assert self.jar.get_header("example.com") == ""
        assert self.jar.get_header("other.com") != ""

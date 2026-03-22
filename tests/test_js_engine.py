import pytest

from pybrowser.js import ToyJSEngine, create_engine


class TestToyJSEngine:
    def test_execute(self):
        e = ToyJSEngine()
        assert e.execute("1 + 2") == 3.0

    def test_set_global(self):
        e = ToyJSEngine()
        e.set_global("x", 42)
        assert e.execute("x") == 42

    def test_native_fn(self):
        e = ToyJSEngine()
        e.set_native_fn("double", lambda x: x * 2)
        assert e.execute("double(5)") == 10.0


class TestCreateEngine:
    def test_toy(self):
        e = create_engine("toy")
        assert isinstance(e, ToyJSEngine)

    def test_auto_returns_engine(self):
        e = create_engine("auto")
        assert e is not None
        assert e.execute("1 + 1") in (2, 2.0)

    def test_quickjs_if_available(self):
        try:
            from pybrowser.js import QuickJSEngine
            e = create_engine("quickjs")
            assert isinstance(e, QuickJSEngine)
            assert e.execute("1 + 1") == 2
        except ImportError:
            pytest.skip("quickjs not installed")

    def test_dukpy_if_available(self):
        try:
            from pybrowser.js import DukpyEngine
            e = create_engine("dukpy")
            assert isinstance(e, DukpyEngine)
        except ImportError:
            pytest.skip("dukpy not installed")

"""Pluggable JavaScript engine interface with three backends:
  - QuickJSEngine: ES2020+ via QuickJS (best modern support)
  - DukpyEngine:   ES5 via Duktape/dukpy
  - ToyJSEngine:   our custom interpreter (always available, ES5 subset)
"""
from __future__ import annotations
from typing import Any, Callable, Optional

from .js_interpreter import Interpreter, NativeFunction, JSFunction, JS_UNDEFINED


class JSEngine:
    """Abstract interface for a JS execution engine."""

    def execute(self, code: str) -> Any:
        raise NotImplementedError

    def call(self, fn_name: str, *args: Any) -> Any:
        raise NotImplementedError

    def set_global(self, name: str, value: Any) -> None:
        raise NotImplementedError

    def set_native_fn(self, name: str, fn: Callable) -> None:
        raise NotImplementedError


class QuickJSEngine(JSEngine):
    """ES2020+ engine via QuickJS (requires `pip install quickjs`)."""

    def __init__(self, debug: bool = False) -> None:
        import quickjs
        self._ctx = quickjs.Context()
        self.debug = debug

    def execute(self, code: str) -> Any:
        try:
            return self._ctx.eval(code)
        except Exception as e:
            if self.debug:
                print(f"[QuickJS] {e}")
            return None

    def call(self, fn_name: str, *args: Any) -> Any:
        args_json = ", ".join(_to_json_arg(a) for a in args)
        return self.execute(f"{fn_name}({args_json})")

    def set_global(self, name: str, value: Any) -> None:
        self.execute(f"var {name} = {_to_json_arg(value)};")

    def set_native_fn(self, name: str, fn: Callable) -> None:
        self._ctx.add_callable(name, fn)


class DukpyEngine(JSEngine):
    """ES5 engine via Duktape/dukpy (requires `pip install dukpy`)."""

    def __init__(self, debug: bool = False) -> None:
        import dukpy
        self._interp = dukpy.JSInterpreter()
        self._py_funcs: dict = {}
        self.debug = debug

    def execute(self, code: str) -> Any:
        try:
            return self._interp.evaljs(code)
        except Exception as e:
            if self.debug:
                print(f"[Dukpy] {e}")
            return None

    def call(self, fn_name: str, *args: Any) -> Any:
        args_json = ", ".join(_to_json_arg(a) for a in args)
        return self.execute(f"{fn_name}({args_json})")

    def set_global(self, name: str, value: Any) -> None:
        self.execute(f"var {name} = {_to_json_arg(value)};")

    def set_native_fn(self, name: str, fn: Callable) -> None:
        safe_name = name.replace(".", "_")
        self._py_funcs[safe_name] = fn
        self._interp.export_function(safe_name, fn)


class ToyJSEngine(JSEngine):
    """Custom toy JS interpreter -- always available, ES5 subset."""

    def __init__(self, debug: bool = False) -> None:
        self.interp = Interpreter()
        self.debug = debug

    def execute(self, code: str) -> Any:
        try:
            return self.interp.execute(code)
        except Exception as e:
            if self.debug:
                print(f"[ToyJS] {e}")
            return JS_UNDEFINED

    def call(self, fn_name: str, *args: Any) -> Any:
        try:
            return self.interp.call_function(fn_name, *args)
        except Exception as e:
            if self.debug:
                print(f"[ToyJS] calling {fn_name}: {e}")
            return JS_UNDEFINED

    def set_global(self, name: str, value: Any) -> None:
        self.interp.global_env.define(name, value)

    def set_native_fn(self, name: str, fn: Callable) -> None:
        self.interp.global_env.define(name, NativeFunction(name, fn))


def _to_json_arg(val: Any) -> str:
    import json
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return json.dumps(val)
    return "null"


def create_engine(prefer: str = "auto") -> JSEngine:
    """Create the best available JS engine.

    prefer: "auto", "quickjs", "dukpy", or "toy"
    Priority for auto: quickjs > dukpy > toy
    """
    if prefer == "toy":
        return ToyJSEngine()

    if prefer == "quickjs":
        import quickjs  # noqa: F401
        return QuickJSEngine()

    if prefer == "dukpy":
        import dukpy  # noqa: F401
        return DukpyEngine()

    for factory in (QuickJSEngine, DukpyEngine):
        try:
            return factory()
        except ImportError:
            continue

    return ToyJSEngine()

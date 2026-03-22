"""Toy JavaScript interpreter: lexer, recursive-descent parser, tree-walking evaluator."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Sentinel values
# ---------------------------------------------------------------------------

class _Undefined:
    def __repr__(self) -> str:
        return "undefined"
    def __bool__(self) -> bool:
        return False

JS_UNDEFINED = _Undefined()


class _BreakSignal(Exception):
    pass

class _ContinueSignal(Exception):
    pass

@dataclass
class _ReturnSignal(Exception):
    value: Any = None


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

KEYWORDS = {
    "var", "let", "const", "function", "return", "if", "else", "while", "for",
    "true", "false", "null", "undefined", "typeof", "new", "this", "break",
    "continue", "in", "of", "instanceof", "do", "switch", "case", "default",
    "throw", "try", "catch", "finally", "delete", "void",
}

@dataclass
class Token:
    kind: str
    value: Any
    line: int


def tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    line = 1
    length = len(source)

    while i < length:
        c = source[i]

        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue

        if source[i:i+2] == "//":
            while i < length and source[i] != "\n":
                i += 1
            continue
        if source[i:i+2] == "/*":
            i += 2
            while i < length - 1 and source[i:i+2] != "*/":
                if source[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue

        if c in "0123456789" or (c == "." and i + 1 < length and source[i+1].isdigit()):
            start = i
            if source[i:i+2] in ("0x", "0X"):
                i += 2
                while i < length and source[i] in "0123456789abcdefABCDEF":
                    i += 1
                tokens.append(Token("NUM", int(source[start:i], 16), line))
            else:
                while i < length and source[i] in "0123456789":
                    i += 1
                if i < length and source[i] == ".":
                    i += 1
                    while i < length and source[i].isdigit():
                        i += 1
                if i < length and source[i] in "eE":
                    i += 1
                    if i < length and source[i] in "+-":
                        i += 1
                    while i < length and source[i].isdigit():
                        i += 1
                tokens.append(Token("NUM", float(source[start:i]), line))
            continue

        if c in ('"', "'", "`"):
            quote = c
            i += 1
            chars: list = []
            while i < length and source[i] != quote:
                if source[i] == "\\" and i + 1 < length:
                    i += 1
                    esc = source[i]
                    chars.append({"n": "\n", "t": "\t", "r": "\r", "\\": "\\",
                                  "'": "'", '"': '"', "`": "`", "/": "/"}.get(esc, esc))
                else:
                    if source[i] == "\n":
                        line += 1
                    chars.append(source[i])
                i += 1
            i += 1
            tokens.append(Token("STR", "".join(chars), line))
            continue

        if c.isalpha() or c == "_" or c == "$":
            start = i
            while i < length and (source[i].isalnum() or source[i] in "_$"):
                i += 1
            word = source[start:i]
            if word in ("true", "false"):
                tokens.append(Token("BOOL", word == "true", line))
            elif word == "null":
                tokens.append(Token("NULL", None, line))
            elif word == "undefined":
                tokens.append(Token("UNDEF", JS_UNDEFINED, line))
            elif word in KEYWORDS:
                tokens.append(Token(word, word, line))
            else:
                tokens.append(Token("ID", word, line))
            continue

        two = source[i:i+2] if i + 1 < length else ""
        three = source[i:i+3] if i + 2 < length else ""

        if three in ("===", "!=="):
            tokens.append(Token(three, three, line)); i += 3; continue
        if two in ("==", "!=", "<=", ">=", "&&", "||", "+=", "-=", "*=",
                    "/=", "=>", "++", "--"):
            tokens.append(Token(two, two, line)); i += 2; continue

        if c in "+-*/%=<>!&|(){}[];:,.?~^":
            tokens.append(Token(c, c, line)); i += 1; continue

        i += 1

    tokens.append(Token("EOF", None, line))
    return tokens


# ---------------------------------------------------------------------------
# AST Nodes (plain dicts for compactness)
# ---------------------------------------------------------------------------

def _n(node_type: str, **kw) -> dict:
    kw["_k"] = node_type
    return kw


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _at(self) -> Token:
        return self.tokens[self.pos]

    def _eat(self, kind: str) -> Token:
        t = self._at()
        if t.kind != kind:
            raise SyntaxError(f"Expected {kind}, got {t.kind} ({t.value!r}) at line {t.line}")
        self.pos += 1
        return t

    def _match(self, *kinds: str) -> bool:
        return self._at().kind in kinds

    def _skip(self, kind: str) -> bool:
        if self._at().kind == kind:
            self.pos += 1
            return True
        return False

    def parse(self) -> dict:
        stmts = []
        while not self._match("EOF"):
            stmts.append(self._statement())
        return _n("Program", body=stmts)

    def _statement(self) -> dict:
        k = self._at().kind
        if k in ("var", "let", "const"):
            return self._var_decl()
        if k == "function":
            return self._func_decl()
        if k == "if":
            return self._if_stmt()
        if k == "while":
            return self._while_stmt()
        if k == "for":
            return self._for_stmt()
        if k == "return":
            return self._return_stmt()
        if k == "break":
            self.pos += 1; self._skip(";")
            return _n("Break")
        if k == "continue":
            self.pos += 1; self._skip(";")
            return _n("Continue")
        if k == "{":
            return self._block()
        if k == "try":
            return self._try_stmt()
        return self._expr_stmt()

    def _var_decl(self) -> dict:
        kind = self._at().value
        self.pos += 1
        decls = []
        while True:
            name = self._eat("ID").value
            init = None
            if self._skip("="):
                init = self._assign_expr()
            decls.append((name, init))
            if not self._skip(","):
                break
        self._skip(";")
        return _n("VarDecl", kind=kind, decls=decls)

    def _func_decl(self) -> dict:
        self._eat("function")
        name = self._eat("ID").value
        params = self._param_list()
        body = self._block()
        return _n("FuncDecl", name=name, params=params, body=body)

    def _param_list(self) -> List[str]:
        self._eat("(")
        params = []
        while not self._match(")"):
            params.append(self._eat("ID").value)
            self._skip(",")
        self._eat(")")
        return params

    def _block(self) -> dict:
        self._eat("{")
        stmts = []
        while not self._match("}"):
            stmts.append(self._statement())
        self._eat("}")
        return _n("Block", body=stmts)

    def _if_stmt(self) -> dict:
        self._eat("if")
        self._eat("(")
        cond = self._expression()
        self._eat(")")
        then = self._statement()
        alt = self._statement() if self._skip("else") else None
        return _n("If", cond=cond, then=then, alt=alt)

    def _while_stmt(self) -> dict:
        self._eat("while")
        self._eat("(")
        cond = self._expression()
        self._eat(")")
        body = self._statement()
        return _n("While", cond=cond, body=body)

    def _for_stmt(self) -> dict:
        self._eat("for")
        self._eat("(")
        init = None
        if not self._match(";"):
            if self._at().kind in ("var", "let", "const"):
                init = self._var_decl()
            else:
                init = self._expression()
                self._skip(";")
        else:
            self._eat(";")
        cond = None if self._match(";") else self._expression()
        self._eat(";")
        update = None if self._match(")") else self._expression()
        self._eat(")")
        body = self._statement()
        return _n("For", init=init, cond=cond, update=update, body=body)

    def _return_stmt(self) -> dict:
        self._eat("return")
        value = None
        if not self._match(";", "}", "EOF"):
            value = self._expression()
        self._skip(";")
        return _n("Return", value=value)

    def _try_stmt(self) -> dict:
        self._eat("try")
        body = self._block()
        catch_param = None
        catch_body = None
        if self._skip("catch"):
            if self._skip("("):
                catch_param = self._eat("ID").value
                self._eat(")")
            catch_body = self._block()
        finally_body = None
        if self._skip("finally"):
            finally_body = self._block()
        return _n("Try", body=body, catch_param=catch_param,
                  catch_body=catch_body, finally_body=finally_body)

    def _expr_stmt(self) -> dict:
        expr = self._expression()
        self._skip(";")
        return _n("ExprStmt", expr=expr)

    # -- expressions (precedence climbing) ----------------------------------

    def _expression(self) -> dict:
        return self._assign_expr()

    def _assign_expr(self) -> dict:
        left = self._ternary()
        if self._at().kind in ("=", "+=", "-=", "*=", "/="):
            op = self._at().value
            self.pos += 1
            right = self._assign_expr()
            return _n("Assign", op=op, target=left, value=right)
        return left

    def _ternary(self) -> dict:
        cond = self._or_expr()
        if self._skip("?"):
            then = self._assign_expr()
            self._eat(":")
            alt = self._assign_expr()
            return _n("Ternary", cond=cond, then=then, alt=alt)
        return cond

    def _or_expr(self) -> dict:
        left = self._and_expr()
        while self._skip("||"):
            left = _n("Binary", op="||", left=left, right=self._and_expr())
        return left

    def _and_expr(self) -> dict:
        left = self._equality()
        while self._skip("&&"):
            left = _n("Binary", op="&&", left=left, right=self._equality())
        return left

    def _equality(self) -> dict:
        left = self._comparison()
        while self._at().kind in ("===", "!==", "==", "!="):
            op = self._at().value; self.pos += 1
            left = _n("Binary", op=op, left=left, right=self._comparison())
        return left

    def _comparison(self) -> dict:
        left = self._addition()
        while self._at().kind in ("<", ">", "<=", ">=", "in", "instanceof"):
            op = self._at().value; self.pos += 1
            left = _n("Binary", op=op, left=left, right=self._addition())
        return left

    def _addition(self) -> dict:
        left = self._multiplication()
        while self._at().kind in ("+", "-"):
            op = self._at().value; self.pos += 1
            left = _n("Binary", op=op, left=left, right=self._multiplication())
        return left

    def _multiplication(self) -> dict:
        left = self._unary()
        while self._at().kind in ("*", "/", "%"):
            op = self._at().value; self.pos += 1
            left = _n("Binary", op=op, left=left, right=self._unary())
        return left

    def _unary(self) -> dict:
        if self._at().kind in ("!", "-", "+", "typeof", "void", "delete"):
            op = self._at().value; self.pos += 1
            return _n("Unary", op=op, arg=self._unary())
        if self._at().kind in ("++", "--"):
            op = self._at().value; self.pos += 1
            return _n("Update", op=op, arg=self._postfix(), prefix=True)
        return self._postfix()

    def _postfix(self) -> dict:
        expr = self._call_member()
        while self._at().kind in ("++", "--"):
            op = self._at().value; self.pos += 1
            expr = _n("Update", op=op, arg=expr, prefix=False)
        return expr

    def _call_member(self) -> dict:
        obj = self._primary()
        while True:
            if self._skip("("):
                args = []
                while not self._match(")"):
                    args.append(self._assign_expr())
                    self._skip(",")
                self._eat(")")
                obj = _n("Call", callee=obj, args=args)
            elif self._skip("."):
                prop = self._eat("ID").value
                obj = _n("Member", obj=obj, prop=prop, computed=False)
            elif self._skip("["):
                prop = self._expression()
                self._eat("]")
                obj = _n("Member", obj=obj, prop=prop, computed=True)
            else:
                break
        return obj

    def _primary(self) -> dict:
        t = self._at()
        if t.kind == "NUM":
            self.pos += 1; return _n("Num", value=t.value)
        if t.kind == "STR":
            self.pos += 1; return _n("Str", value=t.value)
        if t.kind == "BOOL":
            self.pos += 1; return _n("Bool", value=t.value)
        if t.kind == "NULL":
            self.pos += 1; return _n("Null")
        if t.kind == "UNDEF":
            self.pos += 1; return _n("Undef")
        if t.kind == "this":
            self.pos += 1; return _n("This")
        if t.kind == "ID":
            self.pos += 1; return _n("Id", name=t.value)
        if t.kind == "(":
            self.pos += 1
            expr = self._expression()
            self._eat(")")
            if self._at().kind == "=>":
                return self._arrow_rest([expr["name"]] if expr["_k"] == "Id" else [])
            return expr
        if t.kind == "[":
            return self._array_lit()
        if t.kind == "{":
            return self._object_lit()
        if t.kind == "function":
            return self._func_expr()
        if t.kind == "new":
            return self._new_expr()
        raise SyntaxError(f"Unexpected token {t.kind} ({t.value!r}) at line {t.line}")

    def _arrow_rest(self, params: List[str]) -> dict:
        self._eat("=>")
        if self._match("{"):
            body = self._block()
        else:
            body = _n("Return", value=self._assign_expr())
        return _n("Arrow", params=params, body=body)

    def _array_lit(self) -> dict:
        self._eat("[")
        elems = []
        while not self._match("]"):
            elems.append(self._assign_expr())
            self._skip(",")
        self._eat("]")
        return _n("Array", elems=elems)

    def _object_lit(self) -> dict:
        self._eat("{")
        props = []
        while not self._match("}"):
            if self._at().kind == "STR":
                key = self._at().value; self.pos += 1
            elif self._at().kind == "NUM":
                key = str(self._at().value); self.pos += 1
            else:
                key = self._eat("ID").value
            self._eat(":")
            val = self._assign_expr()
            props.append((key, val))
            self._skip(",")
        self._eat("}")
        return _n("Object", props=props)

    def _func_expr(self) -> dict:
        self._eat("function")
        name = None
        if self._match("ID"):
            name = self._eat("ID").value
        params = self._param_list()
        body = self._block()
        return _n("FuncExpr", name=name, params=params, body=body)

    def _new_expr(self) -> dict:
        self._eat("new")
        callee = self._call_member()
        return _n("New", callee=callee)


# ---------------------------------------------------------------------------
# Environment (scope chain)
# ---------------------------------------------------------------------------

class Environment:
    def __init__(self, parent: Optional[Environment] = None) -> None:
        self.vars: Dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.get(name)
        return JS_UNDEFINED

    def set(self, name: str, value: Any) -> None:
        env = self._find(name)
        if env:
            env.vars[name] = value
        else:
            self.vars[name] = value

    def define(self, name: str, value: Any) -> None:
        self.vars[name] = value

    def _find(self, name: str) -> Optional[Environment]:
        if name in self.vars:
            return self
        if self.parent:
            return self.parent._find(name)
        return None


# ---------------------------------------------------------------------------
# JS Function / Native Function wrappers
# ---------------------------------------------------------------------------

@dataclass
class JSFunction:
    name: Optional[str]
    params: List[str]
    body: dict
    closure: Environment

    def __repr__(self) -> str:
        return f"[Function: {self.name or 'anonymous'}]"


@dataclass
class NativeFunction:
    name: str
    fn: Callable

    def __repr__(self) -> str:
        return f"[Native: {self.name}]"

    def __call__(self, *args: Any) -> Any:
        return self.fn(*args)


# ---------------------------------------------------------------------------
# JSObject helper
# ---------------------------------------------------------------------------

class JSObject(dict):
    """A dict subclass that supports prototype chain lookup."""
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._proto: Optional[dict] = None

    def js_get(self, key: str) -> Any:
        if key in self:
            return self[key]
        if self._proto:
            if isinstance(self._proto, JSObject):
                return self._proto.js_get(key)
            return self._proto.get(key, JS_UNDEFINED)
        return JS_UNDEFINED


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

class Interpreter:
    def __init__(self) -> None:
        self.global_env = Environment()
        self._setup_builtins()

    def _setup_builtins(self) -> None:
        self.global_env.define("NaN", float("nan"))
        self.global_env.define("Infinity", float("inf"))
        self.global_env.define("undefined", JS_UNDEFINED)
        self.global_env.define("null", None)

        self.global_env.define("parseInt", NativeFunction("parseInt", self._parseInt))
        self.global_env.define("parseFloat", NativeFunction("parseFloat", self._parseFloat))
        self.global_env.define("isNaN", NativeFunction("isNaN", lambda x: x != x if isinstance(x, float) else False))
        self.global_env.define("String", NativeFunction("String", lambda x="": _to_js_string(x)))
        self.global_env.define("Number", NativeFunction("Number", lambda x=0: _to_js_number(x)))
        self.global_env.define("Boolean", NativeFunction("Boolean", lambda x=False: _to_js_bool(x)))
        self.global_env.define("Array", NativeFunction("Array", lambda *a: list(a)))
        self.global_env.define("Object", NativeFunction("Object", lambda: JSObject()))
        self.global_env.define("Math", self._math_object())
        self.global_env.define("JSON", self._json_object())

    @staticmethod
    def _parseInt(s, radix=10):
        try:
            return int(str(s).strip().split()[0] if s else "0", int(radix) if radix else 10)
        except (ValueError, IndexError):
            return float("nan")

    @staticmethod
    def _parseFloat(s):
        try:
            return float(str(s).strip())
        except ValueError:
            return float("nan")

    @staticmethod
    def _math_object() -> dict:
        import math
        return {
            "PI": math.pi, "E": math.e,
            "floor": NativeFunction("floor", lambda x: int(math.floor(x))),
            "ceil": NativeFunction("ceil", lambda x: int(math.ceil(x))),
            "round": NativeFunction("round", lambda x: int(round(x))),
            "abs": NativeFunction("abs", lambda x: abs(x)),
            "max": NativeFunction("max", lambda *a: max(a) if a else float("-inf")),
            "min": NativeFunction("min", lambda *a: min(a) if a else float("inf")),
            "random": NativeFunction("random", lambda: __import__("random").random()),
            "sqrt": NativeFunction("sqrt", lambda x: math.sqrt(x)),
            "pow": NativeFunction("pow", lambda x, y: math.pow(x, y)),
        }

    @staticmethod
    def _json_object() -> dict:
        import json as _json
        return {
            "stringify": NativeFunction("stringify", lambda o, *a: _json.dumps(o)),
            "parse": NativeFunction("parse", lambda s: _json.loads(s)),
        }

    def execute(self, code: str) -> Any:
        tokens = tokenize(code)
        ast = Parser(tokens).parse()
        return self._exec_program(ast, self.global_env)

    def call_function(self, name: str, *args: Any) -> Any:
        fn = self.global_env.get(name)
        if callable(fn) or isinstance(fn, (JSFunction, NativeFunction)):
            return self._call(fn, list(args), self.global_env)
        raise RuntimeError(f"{name} is not a function")

    # -- exec statements ----------------------------------------------------

    def _exec_program(self, node: dict, env: Environment) -> Any:
        result = JS_UNDEFINED
        for stmt in node["body"]:
            result = self._exec(stmt, env)
        return result

    def _exec(self, node: dict, env: Environment) -> Any:
        k = node["_k"]
        if k == "VarDecl":
            return self._exec_var(node, env)
        if k == "FuncDecl":
            fn = JSFunction(node["name"], node["params"], node["body"], env)
            env.define(node["name"], fn)
            return fn
        if k == "Block":
            child_env = Environment(env)
            result = JS_UNDEFINED
            for s in node["body"]:
                result = self._exec(s, child_env)
            return result
        if k == "If":
            if _to_js_bool(self._eval(node["cond"], env)):
                return self._exec(node["then"], env)
            elif node["alt"]:
                return self._exec(node["alt"], env)
            return JS_UNDEFINED
        if k == "While":
            while _to_js_bool(self._eval(node["cond"], env)):
                try:
                    self._exec(node["body"], env)
                except _BreakSignal:
                    break
                except _ContinueSignal:
                    continue
            return JS_UNDEFINED
        if k == "For":
            return self._exec_for(node, env)
        if k == "Return":
            val = self._eval(node["value"], env) if node["value"] else JS_UNDEFINED
            raise _ReturnSignal(val)
        if k == "Break":
            raise _BreakSignal()
        if k == "Continue":
            raise _ContinueSignal()
        if k == "ExprStmt":
            return self._eval(node["expr"], env)
        if k == "Try":
            return self._exec_try(node, env)
        return self._eval(node, env)

    def _exec_var(self, node: dict, env: Environment) -> Any:
        for name, init_expr in node["decls"]:
            val = self._eval(init_expr, env) if init_expr else JS_UNDEFINED
            env.define(name, val)
        return JS_UNDEFINED

    def _exec_for(self, node: dict, env: Environment) -> Any:
        loop_env = Environment(env)
        if node["init"]:
            if isinstance(node["init"], dict) and node["init"].get("_k") == "VarDecl":
                self._exec(node["init"], loop_env)
            else:
                self._eval(node["init"], loop_env)
        while True:
            if node["cond"] and not _to_js_bool(self._eval(node["cond"], loop_env)):
                break
            try:
                self._exec(node["body"], loop_env)
            except _BreakSignal:
                break
            except _ContinueSignal:
                pass
            if node["update"]:
                self._eval(node["update"], loop_env)
        return JS_UNDEFINED

    def _exec_try(self, node: dict, env: Environment) -> Any:
        try:
            return self._exec(node["body"], env)
        except _ReturnSignal:
            raise
        except Exception as e:
            if node["catch_body"]:
                catch_env = Environment(env)
                if node["catch_param"]:
                    catch_env.define(node["catch_param"], str(e))
                return self._exec(node["catch_body"], catch_env)
        finally:
            if node["finally_body"]:
                self._exec(node["finally_body"], env)
        return JS_UNDEFINED

    # -- eval expressions ---------------------------------------------------

    def _eval(self, node: dict, env: Environment) -> Any:
        if node is None:
            return JS_UNDEFINED
        k = node["_k"]
        if k == "Num":
            return node["value"]
        if k == "Str":
            return node["value"]
        if k == "Bool":
            return node["value"]
        if k == "Null":
            return None
        if k == "Undef":
            return JS_UNDEFINED
        if k == "Id":
            return env.get(node["name"])
        if k == "This":
            return env.get("this")
        if k == "Binary":
            return self._eval_binary(node, env)
        if k == "Unary":
            return self._eval_unary(node, env)
        if k == "Assign":
            return self._eval_assign(node, env)
        if k == "Update":
            return self._eval_update(node, env)
        if k == "Ternary":
            if _to_js_bool(self._eval(node["cond"], env)):
                return self._eval(node["then"], env)
            return self._eval(node["alt"], env)
        if k == "Member":
            return self._eval_member(node, env)
        if k == "Call":
            return self._eval_call(node, env)
        if k == "Array":
            return [self._eval(e, env) for e in node["elems"]]
        if k == "Object":
            obj = JSObject()
            for key, val_node in node["props"]:
                obj[key] = self._eval(val_node, env)
            return obj
        if k in ("FuncExpr", "Arrow"):
            params = node["params"]
            body = node["body"]
            name = node.get("name")
            return JSFunction(name, params, body, env)
        if k == "New":
            return self._eval_new(node, env)
        return JS_UNDEFINED

    def _eval_binary(self, node: dict, env: Environment) -> Any:
        op = node["op"]
        if op == "&&":
            left = self._eval(node["left"], env)
            return left if not _to_js_bool(left) else self._eval(node["right"], env)
        if op == "||":
            left = self._eval(node["left"], env)
            return left if _to_js_bool(left) else self._eval(node["right"], env)

        left = self._eval(node["left"], env)
        right = self._eval(node["right"], env)

        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return _to_js_string(left) + _to_js_string(right)
            return _to_js_number(left) + _to_js_number(right)
        if op == "-": return _to_js_number(left) - _to_js_number(right)
        if op == "*": return _to_js_number(left) * _to_js_number(right)
        if op == "/":
            r = _to_js_number(right)
            return float("nan") if r == 0 else _to_js_number(left) / r
        if op == "%":
            r = _to_js_number(right)
            return float("nan") if r == 0 else _to_js_number(left) % r
        if op in ("===", "!=="):
            eq = left is right if (left is None or isinstance(left, _Undefined)) else left == right
            return eq if op == "===" else not eq
        if op in ("==", "!="):
            eq = _loose_eq(left, right)
            return eq if op == "==" else not eq
        if op == "<": return _to_js_number(left) < _to_js_number(right)
        if op == ">": return _to_js_number(left) > _to_js_number(right)
        if op == "<=": return _to_js_number(left) <= _to_js_number(right)
        if op == ">=": return _to_js_number(left) >= _to_js_number(right)
        if op == "in":
            return left in right if isinstance(right, (dict, list)) else False
        if op == "instanceof":
            return False
        return JS_UNDEFINED

    def _eval_unary(self, node: dict, env: Environment) -> Any:
        op = node["op"]
        if op == "typeof":
            val = self._eval(node["arg"], env)
            return _js_typeof(val)
        val = self._eval(node["arg"], env)
        if op == "!": return not _to_js_bool(val)
        if op == "-": return -_to_js_number(val)
        if op == "+": return _to_js_number(val)
        if op == "void": return JS_UNDEFINED
        return JS_UNDEFINED

    def _eval_assign(self, node: dict, env: Environment) -> Any:
        value = self._eval(node["value"], env)
        target = node["target"]
        op = node["op"]

        if op != "=":
            old = self._eval(target, env)
            if op == "+=":
                if isinstance(old, str) or isinstance(value, str):
                    value = _to_js_string(old) + _to_js_string(value)
                else:
                    value = _to_js_number(old) + _to_js_number(value)
            elif op == "-=": value = _to_js_number(old) - _to_js_number(value)
            elif op == "*=": value = _to_js_number(old) * _to_js_number(value)
            elif op == "/=": value = _to_js_number(old) / _to_js_number(value)

        if target["_k"] == "Id":
            env.set(target["name"], value)
        elif target["_k"] == "Member":
            obj = self._eval(target["obj"], env)
            key = self._member_key(target, env)
            if isinstance(obj, (dict, JSObject)):
                obj[key] = value
            elif isinstance(obj, list) and isinstance(key, (int, float)):
                idx = int(key)
                while len(obj) <= idx:
                    obj.append(JS_UNDEFINED)
                obj[idx] = value
        return value

    def _eval_update(self, node: dict, env: Environment) -> Any:
        target = node["arg"]
        old = _to_js_number(self._eval(target, env))
        new = old + 1 if node["op"] == "++" else old - 1
        dummy_assign = _n("Assign", op="=", target=target, value=_n("Num", value=new))
        self._eval_assign(dummy_assign, env)
        return old if not node["prefix"] else new

    def _eval_member(self, node: dict, env: Environment) -> Any:
        obj = self._eval(node["obj"], env)
        key = self._member_key(node, env)
        return _member_get(obj, key)

    def _member_key(self, node: dict, env: Environment) -> Any:
        if node["computed"]:
            return self._eval(node["prop"], env)
        return node["prop"]

    def _eval_call(self, node: dict, env: Environment) -> Any:
        callee_node = node["callee"]
        args = [self._eval(a, env) for a in node["args"]]

        this_val = JS_UNDEFINED
        if callee_node["_k"] == "Member":
            this_val = self._eval(callee_node["obj"], env)
            fn = _member_get(this_val, self._member_key(callee_node, env))
        else:
            fn = self._eval(callee_node, env)

        return self._call(fn, args, env, this_val)

    def _call(self, fn: Any, args: list, env: Environment, this_val: Any = JS_UNDEFINED) -> Any:
        if isinstance(fn, NativeFunction):
            return fn(*args)
        if isinstance(fn, JSFunction):
            call_env = Environment(fn.closure)
            call_env.define("this", this_val)
            for i, param in enumerate(fn.params):
                call_env.define(param, args[i] if i < len(args) else JS_UNDEFINED)
            call_env.define("arguments", args)
            try:
                self._exec(fn.body, call_env)
            except _ReturnSignal as r:
                return r.value
            return JS_UNDEFINED
        if callable(fn):
            return fn(*args)
        return JS_UNDEFINED

    def _eval_new(self, node: dict, env: Environment) -> Any:
        callee_node = node["callee"]
        if callee_node["_k"] == "Call":
            fn = self._eval(callee_node["callee"], env)
            args = [self._eval(a, env) for a in callee_node["args"]]
        else:
            fn = self._eval(callee_node, env)
            args = []
        obj = JSObject()
        self._call(fn, args, env, obj)
        return obj


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def _to_js_string(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, _Undefined):
        return "undefined"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float) and val == int(val) and not (val != val):
        return str(int(val))
    if isinstance(val, (dict, JSObject)):
        return "[object Object]"
    if isinstance(val, list):
        return ",".join(_to_js_string(v) for v in val)
    return str(val)


def _to_js_number(val: Any) -> float:
    if val is None or isinstance(val, _Undefined):
        return 0.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return float("nan")
    return float("nan")


def _to_js_bool(val: Any) -> bool:
    if val is None or isinstance(val, _Undefined):
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0 and val == val
    if isinstance(val, str):
        return len(val) > 0
    return True


def _loose_eq(a: Any, b: Any) -> bool:
    if a is None and isinstance(b, _Undefined):
        return True
    if isinstance(a, _Undefined) and b is None:
        return True
    if a is None and b is None:
        return True
    if isinstance(a, _Undefined) and isinstance(b, _Undefined):
        return True
    try:
        return a == b
    except Exception:
        return False


def _js_typeof(val: Any) -> str:
    if isinstance(val, _Undefined):
        return "undefined"
    if val is None:
        return "object"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, (JSFunction, NativeFunction)) or callable(val):
        return "function"
    return "object"


# ---------------------------------------------------------------------------
# Built-in method dispatch for member access
# ---------------------------------------------------------------------------

def _member_get(obj: Any, key: Any) -> Any:
    if isinstance(obj, (dict, JSObject)):
        if isinstance(obj, JSObject):
            return obj.js_get(key)
        return obj.get(key, JS_UNDEFINED) if isinstance(key, str) else JS_UNDEFINED

    if isinstance(obj, str):
        return _string_member(obj, key)

    if isinstance(obj, list):
        return _array_member(obj, key)

    return JS_UNDEFINED


def _string_member(s: str, key: Any) -> Any:
    if key == "length":
        return len(s)
    if key == "indexOf":
        return NativeFunction("indexOf", lambda sub, start=0: s.find(sub, int(start)))
    if key == "slice":
        return NativeFunction("slice", lambda a=0, b=None: s[int(a):int(b) if b is not None else len(s)])
    if key == "substring":
        return NativeFunction("substring", lambda a=0, b=None: s[int(a):int(b) if b is not None else len(s)])
    if key == "split":
        return NativeFunction("split", lambda sep=None, limit=-1: s.split(sep) if sep else list(s))
    if key == "trim":
        return NativeFunction("trim", lambda: s.strip())
    if key == "toUpperCase":
        return NativeFunction("toUpperCase", lambda: s.upper())
    if key == "toLowerCase":
        return NativeFunction("toLowerCase", lambda: s.lower())
    if key == "includes":
        return NativeFunction("includes", lambda sub: sub in s)
    if key == "startsWith":
        return NativeFunction("startsWith", lambda sub: s.startswith(sub))
    if key == "endsWith":
        return NativeFunction("endsWith", lambda sub: s.endswith(sub))
    if key == "replace":
        return NativeFunction("replace", lambda old, new: s.replace(str(old), str(new), 1))
    if key == "charAt":
        return NativeFunction("charAt", lambda i=0: s[int(i)] if 0 <= int(i) < len(s) else "")
    if key == "charCodeAt":
        return NativeFunction("charCodeAt", lambda i=0: ord(s[int(i)]) if 0 <= int(i) < len(s) else float("nan"))
    if isinstance(key, (int, float)):
        idx = int(key)
        return s[idx] if 0 <= idx < len(s) else JS_UNDEFINED
    return JS_UNDEFINED


def _array_member(arr: list, key: Any) -> Any:
    if key == "length":
        return len(arr)
    if key == "push":
        return NativeFunction("push", lambda *items: [arr.append(i) for i in items] and len(arr) or len(arr))
    if key == "pop":
        return NativeFunction("pop", lambda: arr.pop() if arr else JS_UNDEFINED)
    if key == "shift":
        return NativeFunction("shift", lambda: arr.pop(0) if arr else JS_UNDEFINED)
    if key == "unshift":
        def _unshift(*items):
            for item in reversed(items):
                arr.insert(0, item)
            return len(arr)
        return NativeFunction("unshift", _unshift)
    if key == "indexOf":
        return NativeFunction("indexOf", lambda v: arr.index(v) if v in arr else -1)
    if key == "includes":
        return NativeFunction("includes", lambda v: v in arr)
    if key == "join":
        return NativeFunction("join", lambda sep=",": sep.join(_to_js_string(v) for v in arr))
    if key == "slice":
        return NativeFunction("slice", lambda a=0, b=None: arr[int(a):int(b) if b is not None else len(arr)])
    if key == "splice":
        def _splice(start=0, count=None, *items):
            s = int(start)
            c = int(count) if count is not None else len(arr) - s
            removed = arr[s:s+c]
            arr[s:s+c] = list(items)
            return removed
        return NativeFunction("splice", _splice)
    if key == "concat":
        return NativeFunction("concat", lambda *others: arr + [i for o in others for i in (o if isinstance(o, list) else [o])])
    if key == "reverse":
        return NativeFunction("reverse", lambda: (arr.reverse(), arr)[1])
    if key == "sort":
        return NativeFunction("sort", lambda fn=None: (arr.sort(), arr)[1])
    if key == "forEach":
        def _forEach(fn):
            interp = fn  # JSFunction or NativeFunction
            for i, v in enumerate(arr):
                if isinstance(interp, NativeFunction):
                    interp(v, i, arr)
            return JS_UNDEFINED
        return NativeFunction("forEach", _forEach)
    if key == "map":
        def _map(fn):
            result = []
            for i, v in enumerate(arr):
                if isinstance(fn, NativeFunction):
                    result.append(fn(v, i, arr))
                else:
                    result.append(v)
            return result
        return NativeFunction("map", _map)
    if key == "filter":
        def _filter(fn):
            result = []
            for i, v in enumerate(arr):
                if isinstance(fn, NativeFunction) and _to_js_bool(fn(v, i, arr)):
                    result.append(v)
            return result
        return NativeFunction("filter", _filter)
    if isinstance(key, (int, float)):
        idx = int(key)
        return arr[idx] if 0 <= idx < len(arr) else JS_UNDEFINED
    return JS_UNDEFINED

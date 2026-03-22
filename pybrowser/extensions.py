"""Extensions system: load userscript JS files that run on every page."""
from __future__ import annotations

import os
from typing import List

EXTENSIONS_DIR = os.path.expanduser("~/.pybrowser/extensions")


class ExtensionManager:
    def __init__(self) -> None:
        self.scripts: List[dict] = []
        self._load()

    def _load(self) -> None:
        self.scripts = []
        if not os.path.isdir(EXTENSIONS_DIR):
            os.makedirs(EXTENSIONS_DIR, exist_ok=True)
            self._create_example()
            return

        for f in sorted(os.listdir(EXTENSIONS_DIR)):
            if f.endswith(".js"):
                path = os.path.join(EXTENSIONS_DIR, f)
                try:
                    with open(path) as fh:
                        code = fh.read()
                    meta = self._parse_meta(code)
                    meta["file"] = f
                    meta["code"] = code
                    meta["enabled"] = True
                    self.scripts.append(meta)
                except Exception:
                    pass

    @staticmethod
    def _parse_meta(code: str) -> dict:
        meta: dict = {"name": "Unknown", "match": "*", "description": ""}
        for line in code.split("\n")[:20]:
            line = line.strip()
            if line.startswith("// @name"):
                meta["name"] = line.split("@name", 1)[1].strip()
            elif line.startswith("// @match"):
                meta["match"] = line.split("@match", 1)[1].strip()
            elif line.startswith("// @description"):
                meta["description"] = line.split("@description", 1)[1].strip()
        return meta

    def _create_example(self) -> None:
        example = os.path.join(EXTENSIONS_DIR, "example.js")
        if not os.path.exists(example):
            with open(example, "w") as f:
                f.write("""// @name Example Extension
// @match *
// @description Logs a message on every page load
console.log("[Extension] Example extension loaded on: " + location.href);
""")

    def get_scripts_for(self, url: str) -> List[str]:
        result = []
        for script in self.scripts:
            if not script.get("enabled"):
                continue
            match = script.get("match", "*")
            if match == "*" or match in url:
                result.append(script["code"])
        return result

    def list_extensions(self) -> List[dict]:
        return [{"name": s["name"], "file": s["file"], "description": s.get("description", ""),
                 "enabled": s.get("enabled", True)} for s in self.scripts]

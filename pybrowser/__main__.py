"""Entry point for `python -m pybrowser [--quickjs|--dukpy|--toy] [url]`."""
import sys

from .browser import Browser


def main():
    engine = "auto"
    args = sys.argv[1:]
    for flag, name in [("--toy", "toy"), ("--dukpy", "dukpy"), ("--quickjs", "quickjs")]:
        if flag in args:
            engine = name
            args.remove(flag)
            break
    url = args[0] if args else "https://browser.engineering/"
    browser = Browser(js_engine=engine)
    browser.load(url)
    browser.run()


if __name__ == "__main__":
    main()

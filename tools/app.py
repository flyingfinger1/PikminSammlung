"""Entry point of the packaged app (PikminHerbarium.exe): without arguments the menu, otherwise
one step of the pipeline, e.g. `PikminHerbarium.exe parse captures/<run>`. The menu calls the
steps this way, as the packaged app has no separate Python to run the scripts with.
"""
import sys


def command(name):
    # plain imports, so PyInstaller sees and bundles every step
    if name == "capture":
        import capture_adb as module
    elif name == "parse":
        import parse_captures as module
    elif name == "diff":
        import diff_capture as module
    elif name == "apply":
        import apply_capture as module
    elif name == "build":
        import build_page as module
    elif name == "publish":
        import publish as module
    elif name == "seeds":
        import parse_seeds as module
    else:
        return None
    return module.main


def main():
    # a console shows umlauts anyway; pipes and files would get the ANSI code page
    for stream in (sys.stdout, sys.stderr):
        if stream and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        import pikmin
        try:
            pikmin.main()
        except (KeyboardInterrupt, EOFError):
            print()
        return
    step = command(sys.argv[1])
    if step is None:
        sys.exit(f"unknown command: {sys.argv[1]} (capture, parse, diff, apply, build, publish, seeds)")
    sys.argv = [f"{sys.argv[0]} {sys.argv[1]}", *sys.argv[2:]]
    step()


if __name__ == "__main__":
    main()

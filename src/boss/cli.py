import argparse

from boss import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="boss", description="Fund an idea; a boss agent builds it."
    )
    parser.add_argument("--version", action="version", version=f"boss {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0

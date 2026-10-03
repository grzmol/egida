"""`egida` configures and runs the AI Control Layer in a terminal UI; `egida run` starts the proxy
from the run profile in the foreground (what `make run` does, with the profile's settings)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from control_layer.egida.document import DocumentError, PolicyDocument
from control_layer.egida.runner import (
    PROFILE_PATH,
    ProfileError,
    Proxy,
    exec_foreground,
    load_profile,
)
from control_layer.egida.schema import detector_params
from control_layer.egida.screens import build_app
from control_layer.egida.session import Session
from control_layer.egida.term import Terminal
from control_layer.egida.theme import Style, detect_color_mode

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="egida",
        description="Configure and run the AI Control Layer (policy, run settings, proxy process).",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=PROFILE_PATH,
        help=f"run profile with host, port and file paths (default: {PROFILE_PATH})",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="start the proxy in the foreground with the run profile")
    args = parser.parse_args(argv)

    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"egida: {exc}", file=sys.stderr)
        return 2
    if args.command == "run":
        exec_foreground(profile)

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "egida: needs an interactive terminal; `egida run` starts the proxy without one",
            file=sys.stderr,
        )
        return 2
    try:
        doc = PolicyDocument.open(profile.policy)
    except DocumentError as exc:
        print(
            f"egida: {exc}\nFix the file in an editor or point `policy:` in {args.profile} "
            "at another policy.",
            file=sys.stderr,
        )
        return 2

    proxy = Proxy()
    session = Session(
        doc=doc,
        profile=profile,
        profile_path=args.profile,
        proxy=proxy,
        param_models=detector_params(),
    )
    app = build_app(session, style=Style(detect_color_mode()))
    try:
        with Terminal() as terminal:
            app.run(terminal)
    finally:
        proxy.stop()  # no orphan proxy when Egida exits, also after a crash
    return 0


if __name__ == "__main__":
    sys.exit(main())

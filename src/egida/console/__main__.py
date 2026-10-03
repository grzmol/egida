"""`egd` opens the Egida console and starts the proxy (the setup wizard first when there is no run
profile yet); `egd setup` opens the wizard; `egd run` starts the proxy from the run profile in the
foreground without a UI (what `make run` does, with the profile's settings); `egd launch <id>`
starts a launch-mode harness against the running proxy."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from egida.console.document import DocumentError, PolicyDocument
from egida.console.harnesses import REGISTRY, by_id
from egida.console.harnesses.base import Harness, HarnessEnv, HarnessError
from egida.console.run_screens import autostart
from egida.console.runner import (
    PROFILE_PATH,
    ProfileError,
    Proxy,
    RunProfile,
    exec_foreground,
    load_profile,
)
from egida.console.schema import detector_params
from egida.console.screens import build_app
from egida.console.session import Session
from egida.console.term import Terminal
from egida.console.theme import Style, detect_color_mode
from egida.console.wizard import start_command, wizard_view

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="egd",
        description="Configure and run the Egida proxy (policy, run settings, proxy process).",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=PROFILE_PATH,
        help=f"run profile with host, port and file paths (default: {PROFILE_PATH})",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="start the proxy in the foreground with the run profile")
    commands.add_parser("setup", help="open the setup wizard (model, harnesses, proxy address)")
    launch = commands.add_parser("launch", help="start a harness that is routed per launch")
    launch.add_argument("harness", help="harness id, for example antigravity-cli")
    launch.add_argument("args", nargs=argparse.REMAINDER, help="arguments for the harness")
    args = parser.parse_args(argv)
    first_run = not args.profile.exists()

    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"egd: {exc}", file=sys.stderr)
        return 2
    if args.command == "run":
        exec_foreground(profile)
    if args.command == "launch":
        return _launch(profile, args.harness, args.args)

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "egd: needs an interactive terminal; `egd run` starts the proxy without one",
            file=sys.stderr,
        )
        return 2
    try:
        doc = PolicyDocument.open(profile.policy)
    except DocumentError as exc:
        print(
            f"egd: {exc}\nFix the file in an editor or point `policy:` in {args.profile} "
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

    def after_first_run() -> None:
        if not proxy.running:
            autostart(session)

    try:
        if args.command == "setup":
            app.push(wizard_view(session, on_done=lambda: None))
        elif first_run:
            app.push(wizard_view(session, first_run=True, on_done=after_first_run))
        else:
            autostart(session)
        with Terminal() as terminal:
            app.run(terminal)
    finally:
        proxy.stop()  # no orphan proxy when the console exits, also after a crash
    return 0


def _launch(profile: RunProfile, harness_id: str, extra: list[str]) -> int:
    """Replace this process with the harness, its environment pointed at the running proxy."""
    try:
        harness = by_id(harness_id)
    except KeyError:
        ids = ", ".join(h.id for h in REGISTRY if h.mode != "unavailable")
        print(f"egd: unknown harness {harness_id!r}; `egd launch` takes: {ids}", file=sys.stderr)
        return 2
    if harness.mode == "unavailable":
        print(f"egd: {harness.name} cannot use Egida: {harness.note}", file=sys.stderr)
        return 2
    try:
        command, env = harness.launch(HarnessEnv.current(), extra)
    except HarnessError as exc:
        if type(harness).launch is Harness.launch:  # no launch of its own
            print(
                f"egd: {harness.name} is not started with `egd launch`: run "
                f"`{start_command(harness)}`; egd configured it already. {harness.note}",
                file=sys.stderr,
            )
        else:
            print(f"egd: {exc}", file=sys.stderr)
        return 2
    if Proxy().health(profile) is None:
        print(
            f"egd: proxy not reachable at {profile.base_url}; start it with `egd` or `egd run`",
            file=sys.stderr,
        )
        return 2
    os.execvpe(command[0], command, os.environ | env)  # noqa: S606 (argv from the harness registry)


if __name__ == "__main__":
    sys.exit(main())

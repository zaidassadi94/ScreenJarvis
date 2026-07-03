"""ScreenJarvis CLI: record / compile / last / synth."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import session as S
from .config import Config, load_config

STT_CHOICES = ["auto", "openai", "groq", "json"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sj", description="Push-to-talk dictation that can see your screen."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="record a session (mic + screen + cursor), then compile it")
    p_rec.add_argument("--hold", nargs="?", const="", default=None, metavar="KEY",
                       help="hold-to-record on a global key (default key from config, e.g. alt_r); "
                            "without this flag, recording starts immediately and Enter stops it")
    p_rec.add_argument("--stt", choices=STT_CHOICES, default=None)
    p_rec.add_argument("--no-compile", action="store_true")
    p_rec.add_argument("--no-open", action="store_true")
    p_rec.add_argument("--max-secs", type=float, default=None)
    _add_mode_flags(p_rec)

    p_com = sub.add_parser("compile", help="(re)compile a session bundle into transcript.md")
    p_com.add_argument("session", help="session directory, or 'last'")
    p_com.add_argument("--stt", choices=STT_CHOICES, default=None,
                       help="default: reuse raw/transcript.json when present, else auto")
    _add_mode_flags(p_com)

    p_last = sub.add_parser("last", help="print the latest session directory")
    p_last.add_argument("--open", action="store_true")

    p_syn = sub.add_parser("synth", help="generate a synthetic session (dev/demo; no mic or screen needed)")
    p_syn.add_argument("--out", type=Path, default=Path("synth-session"))

    args = parser.parse_args(argv)
    cfg = load_config()
    handlers = {"record": cmd_record, "compile": cmd_compile, "last": cmd_last, "synth": cmd_synth}
    return handlers[args.command](cfg, args)


def _add_mode_flags(parser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--smart", dest="smart", action="store_const", const="on", default=None,
                       help="have Claude plan the document (prose cleanup, figure choice, captions)")
    group.add_argument("--basic", dest="smart", action="store_const", const="off",
                       help="heuristic-only compile: trigger phrases + cursor log, fully offline")


def cmd_record(cfg: Config, args) -> int:
    from .recorder.record import record_session

    if args.max_secs:
        cfg.max_secs = args.max_secs
    hold = None
    if args.hold is not None:
        hold = args.hold or cfg.hold_key
    try:
        sdir = record_session(cfg, hold=hold)
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(
            f"could not start capture: {exc}\n"
            "On macOS: grant Microphone, Screen Recording, and Accessibility permissions "
            "to your terminal (System Settings → Privacy & Security), then retry."
        )
    print(f"session: {sdir}")
    if args.no_compile:
        print(f"compile later with: sj compile {sdir}")
        return 0
    return _compile_and_report(cfg, sdir, args.stt, smart=args.smart,
                               open_after=cfg.open_after and not args.no_open)


def cmd_compile(cfg: Config, args) -> int:
    return _compile_and_report(cfg, _resolve_session(cfg, args.session), args.stt,
                               smart=args.smart, open_after=False)


def cmd_last(cfg: Config, args) -> int:
    latest = S.latest_session(cfg.sessions_dir)
    if not latest:
        raise SystemExit(f"No sessions in {cfg.sessions_dir}")
    print(latest)
    if args.open and sys.platform == "darwin":
        subprocess.run(["open", str(latest)], check=False)
    return 0


def cmd_synth(cfg: Config, args) -> int:
    from .devtools.synth import make_synthetic_session

    sdir = make_synthetic_session(args.out)
    print(f"synthetic session: {sdir}")
    print(f"compile it with: sj compile {sdir}")
    return 0


def _resolve_session(cfg: Config, ref: str) -> Path:
    if ref == "last":
        latest = S.latest_session(cfg.sessions_dir)
        if not latest:
            raise SystemExit(f"No sessions in {cfg.sessions_dir}")
        return latest
    path = Path(ref).expanduser()
    if not S.is_session_dir(path):
        raise SystemExit(f"{path} is not a session directory")
    return path


def _compile_and_report(cfg: Config, sdir: Path, stt: str | None, *,
                        smart: str | None = None, open_after: bool) -> int:
    from .compiler.compile import compile_session
    from .compiler.render import fmt_clock

    try:
        result = compile_session(sdir, cfg, stt=stt, smart=smart)
    except SystemExit as exc:
        print(f"compile failed: {exc}", file=sys.stderr)
        print(f"the recording is safe — retry with: sj compile {sdir}", file=sys.stderr)
        return 1
    mode = f"smart ({cfg.llm_model})" if result.mode == "smart" else "basic (heuristics)"
    print(f"{result.words} words · {result.segments} segments · "
          f"{len(result.figures)} figure(s) · {mode}")
    for n, fig in enumerate(result.figures, start=1):
        print(f"  fig-{n:02d} ← {fig.label} at {fmt_clock(fig.t)} ({fig.via})")
    print(result.md_path)
    if open_after and sys.platform == "darwin":
        subprocess.run(["open", str(result.md_path)], check=False)
    return 0

"""CLI for the felix-alert bus.

Runnable as ``python3 -m scripts.common.alert_bus <sub> …`` with two
subcommands:

``emit``
    Build an :class:`Alert` from flags and deliver it. **Best-effort by
    default → always exits 0** after attempting delivery (logging the
    ``AlertResult``), so a cron/audit caller never fails because ntfy was
    down. ``--strict`` makes the exit code reflect ``AlertResult.ok``.

``self-test``
    Emit a known ``info`` alert and **exit non-zero if not delivered** — it
    exists to prove the delivery path from a given runtime context.
"""

from __future__ import annotations

import argparse
import sys

from . import emit
from .model import Alert, AlertResult, Severity


def _parse_detail(raw: str) -> tuple[str, str]:
    """Parse a ``key=value`` detail flag; value may contain ``=``."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"--detail expects key=value, got {raw!r}"
        )
    key, value = raw.split("=", 1)
    if not key:
        raise argparse.ArgumentTypeError(f"--detail key must be non-empty: {raw!r}")
    return key, value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.common.alert_bus",
        description="felix-alert bus CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    emit_p = sub.add_parser("emit", help="emit a single alert")
    emit_p.add_argument("--source", required=True)
    emit_p.add_argument(
        "--severity",
        required=True,
        choices=[s.value for s in Severity],
    )
    emit_p.add_argument("--title", required=True)
    emit_p.add_argument("--description", required=True)
    emit_p.add_argument("--action", default=None)
    emit_p.add_argument(
        "--detail",
        action="append",
        default=[],
        type=_parse_detail,
        metavar="key=value",
        help="structured detail; may repeat",
    )
    emit_p.add_argument(
        "--detail-stdin",
        action="store_true",
        help='fold piped stdin text into details["stdin"]',
    )
    emit_p.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when delivery fails (default is best-effort exit 0)",
    )

    sub.add_parser("self-test", help="emit a known info alert; exit non-zero if not delivered")

    return parser


def _log_result(result: AlertResult) -> None:
    status = "ok" if result.ok else "FAILED"
    print(
        f"[alert_bus] delivery {status} "
        f"(reason={result.reason}, topic_configured={result.topic_configured})",
        file=sys.stderr,
    )


def _cmd_emit(args: argparse.Namespace) -> int:
    details: dict[str, str] = {key: value for key, value in args.detail}
    if args.detail_stdin:
        details["stdin"] = sys.stdin.read()

    alert = Alert(
        source=args.source,
        severity=Severity(args.severity),
        title=args.title,
        description=args.description,
        action=args.action,
        details=details,
    )
    result = emit(alert)
    _log_result(result)

    if args.strict and not result.ok:
        return 1
    return 0


def _cmd_self_test() -> int:
    alert = Alert(
        source="alert-bus/self-test",
        severity=Severity.INFO,
        title="felix-alert bus self-test",
        description="Self-test alert proving the delivery path from this runtime context.",
        details={"probe": "self-test"},
    )
    result = emit(alert)
    _log_result(result)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "emit":
        return _cmd_emit(args)
    if args.command == "self-test":
        return _cmd_self_test()
    parser.error(f"unknown command: {args.command}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())

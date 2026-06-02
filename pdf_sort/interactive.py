"""Interactive per-file confirmation prompts (stdlib only)."""

from __future__ import annotations

import logging
import sys
from typing import Callable

logger = logging.getLogger(__name__)


def _ask(prompt: str, default: str = "y") -> str:
    """Prompt user; return normalized single-letter answer.

    Prompt is written to stderr so stdout stays clean for machine-readable
    output (e.g. ``--format json``).
    """
    suffix = f" [{'Y/n/e/all/none' if default == 'y' else 'y/N/e/all/none'}]"
    try:
        print(f"{prompt}{suffix}: ", file=sys.stderr, end="")
        sys.stderr.flush()
        raw = input().strip().lower()
    except EOFError:
        return default
    return raw or default


def confirm_rename(
    item: dict,
    prompt_fn: Callable[[str, str], str] | None = None,
) -> bool:
    """Ask user to confirm a rename. Returns True if approved.

    Args:
        item: plan item with keys ``original``, ``new_name``, ``info``.
        prompt_fn: optional injectable prompt for testing. Signature
            ``(prompt, default) -> answer``.
    """
    ask = prompt_fn or _ask
    info = item["info"]
    amt = f"${info.amount:,.2f}" if info.amount is not None else "?"
    dt = info.date.strftime("%d %b %Y") if info.date else "?"
    label = (
        f"  {item['original']}\n"
        f"    → {item['new_name']}\n"
        f"      ({info.source_bank} → {info.dest_bank}, {amt}, {dt})"
    )
    print(label)
    answer = ask("Rename?", default="y")
    if answer in ("a", "all"):
        return True
    if answer in ("n", "no", "none"):
        return False
    return answer in ("y", "yes", "")


def filter_plan_interactive(
    plan: list[dict],
    prompt_fn: Callable[[str, str], str] | None = None,
) -> list[dict]:
    """Interactively filter a plan, returning only approved items.

    "all" approves the current and all subsequent items. "none" rejects
    the current and all subsequent items.
    """
    ask = prompt_fn or _ask
    approved: list[dict] = []
    approve_all = False
    reject_all = False

    for item in plan:
        if item.get("new_name") is None:
            logger.info("Skipping incomplete record: %s", item["original"])
            continue
        if reject_all:
            continue
        if approve_all:
            approved.append(item)
            continue
        info = item["info"]
        amt = f"${info.amount:,.2f}" if info.amount is not None else "?"
        dt = info.date.strftime("%d %b %Y") if info.date else "?"
        print(
            f"  {item['original']}\n"
            f"    → {item['new_name']}\n"
            f"      ({info.source_bank} → {info.dest_bank}, {amt}, {dt})",
            file=sys.stderr,
        )
        answer = ask("Rename?", default="y")
        if answer in ("a", "all"):
            approve_all = True
            approved.append(item)
        elif answer in ("n", "no", "none"):
            if answer == "none":
                reject_all = True
            # else: just this one
        elif answer in ("y", "yes", ""):
            approved.append(item)
        else:
            logger.warning("Unknown answer %r — skipping", answer)

    return approved

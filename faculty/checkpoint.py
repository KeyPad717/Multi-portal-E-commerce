"""
checkpoint.py — Save/load pipeline state so the pipeline
can be paused and resumed at any stage without data loss.
"""

import json
import os
import time
from pathlib import Path

CHECKPOINT_FILE = "output/checkpoint.json"
Path("output").mkdir(exist_ok=True)

STAGES = [
    "scraped",
    "chunked",
    "enriched",
    "triples",
    "owl"
]


def load() -> dict:
    """Load checkpoint from disk, or return a fresh state."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            cp = json.load(f)
        print(f"[checkpoint] Loaded existing checkpoint. Stage: {cp.get('stage', 'None')}")
        return cp
    print("[checkpoint] No checkpoint found — starting fresh.")
    return {
        "stage": None,
        "tokens_used": 0,
        "paused": False,
        "pause_reason": "",
        "last_saved": None,
        "data": {}
    }


def save(cp: dict):
    """Persist checkpoint to disk."""
    cp["last_saved"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2, ensure_ascii=False)
    print(f"  [checkpoint] ✓ Saved at stage: {cp['stage']} | tokens used: {cp['tokens_used']}")


def mark_stage(cp: dict, stage: str, data_key: str, value):
    """Record completion of a stage and save."""
    cp["stage"] = stage
    cp["data"][data_key] = value
    save(cp)


def check_token_budget(cp: dict, tokens_to_use: int, limit: int) -> bool:
    """
    Check if the pipeline has enough token budget remaining.
    Returns True if OK to proceed, False if limit would be exceeded.
    Saves checkpoint with pause state if exceeded.
    """
    projected = cp["tokens_used"] + tokens_to_use
    if projected >= limit:
        cp["paused"] = True
        cp["pause_reason"] = (
            f"Token budget exhausted. Limit={limit}, "
            f"Used={cp['tokens_used']}, Needed={tokens_to_use}. "
            f"Wait for quota reset (usually 24h) then re-run."
        )
        save(cp)
        print(f"\n{'='*60}")
        print(f"  ⏸  PIPELINE PAUSED")
        print(f"  Reason: {cp['pause_reason']}")
        print(f"  All progress saved to {CHECKPOINT_FILE}")
        print(f"  Re-run `python main.py` when quota resets.")
        print(f"{'='*60}\n")
        return False

    cp["tokens_used"] += tokens_to_use
    return True


def reset():
    """Delete checkpoint to start from scratch."""
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("[checkpoint] Reset complete — deleted checkpoint.")
    else:
        print("[checkpoint] Nothing to reset.")

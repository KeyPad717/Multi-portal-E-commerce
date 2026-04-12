"""
main.py — Pipeline orchestrator.
Runs: Scrape → Chunk → LLM Enrich → RDF Triples → OWL
Supports full pause/resume via checkpoint.json.

Usage:
    python main.py           # run or resume
    python main.py --reset   # wipe checkpoint, start fresh
    python main.py --status  # show current checkpoint state
"""

import os
import sys
import json
from dotenv import load_dotenv
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


# ── Validate env before importing heavy modules ───────────
def _check_env():
    key = os.getenv("OPENROUTER_API_KEY", "")
    
    if not key:
        print("\n❌  ERROR: OPENROUTER_API_KEY not set in .env file")
        print("   Get key at: https://openrouter.ai/keys")
        print("   Then set: OPENROUTER_API_KEY=your_key\n")
        sys.exit(1)

    url = os.getenv("TARGET_URL", "")
    if not url:
        print("\n❌  ERROR: TARGET_URL not set in .env file\n")
        sys.exit(1)


def _show_status():
    from checkpoint import load
    cp = load()
    print("\n── Pipeline Status ──────────────────────────────")
    print(f"  Stage        : {cp.get('stage', 'Not started')}")
    print(f"  Tokens used  : {cp.get('tokens_used', 0)}")
    print(f"  Paused       : {cp.get('paused', False)}")
    print(f"  Last saved   : {cp.get('last_saved', 'N/A')}")
    if cp.get("pause_reason"):
        print(f"  Pause reason : {cp['pause_reason']}")
    data = cp.get("data", {})
    if data:
        print(f"  Cached data  : {list(data.keys())}")
    print("─────────────────────────────────────────────────\n")


def run():
    _check_env()

    URL         = os.getenv("TARGET_URL", "")
    TOKEN_LIMIT = int(os.getenv("TOKEN_LIMIT", "12000"))
    CHUNK_SIZE  = int(os.getenv("CHUNK_SIZE", "2000"))

    from checkpoint import load, mark_stage, save
    from scraper import scrape
    from chunker import chunk_data
    from enricher import enrich_all_chunks
    from triple_builder import build_graph
    from owl_writer import save_owl

    cp = load()

    # ── Handle paused state ───────────────────────────────
    if cp.get("paused"):
        print(f"\n⚠   Pipeline was previously paused.")
        print(f"    Reason: {cp['pause_reason']}")
        print(f"    Tokens used so far: {cp['tokens_used']}")
        ans = input("\n  Resume now? (y/n): ").strip().lower()
        if ans != "y":
            print("  Exiting. Re-run when ready to resume.\n")
            sys.exit(0)
        cp["paused"] = False
        cp["pause_reason"] = ""
        save(cp)

    print(f"\n{'='*58}")
    print(f"  OWL PIPELINE — IIITB Faculty Profile")
    print(f"{'='*58}")
    print(f"  URL         : {URL}")
    print(f"  Token limit : {TOKEN_LIMIT:,}")
    print(f"  Chunk size  : {CHUNK_SIZE:,}")
    print(f"  Resume from : {cp['stage'] or 'beginning'}")
    print(f"{'='*58}\n")

    completed_stages = []
    if cp["stage"]:
        from checkpoint import STAGES
        idx = STAGES.index(cp["stage"]) \
              if cp["stage"] in STAGES else -1
        completed_stages = STAGES[:idx+1]

    # ──────────────────────────────────────────────────────
    # STAGE 1: SCRAPE
    # ──────────────────────────────────────────────────────
    if "scraped" not in completed_stages:
        print("► STAGE 1: Scraping webpage...")
        raw_data = scrape(URL)
        mark_stage(cp, "scraped", "raw", raw_data)

        # Save a clean copy of scraped JSON
        with open("output/scraped_data.json", "w",
                  encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2,
                      ensure_ascii=False)
        print(f"  [main] Raw data saved → "
              f"output/scraped_data.json")
    else:
        raw_data = cp["data"]["raw"]
        print(f"► STAGE 1: Scrape (cached) ✓")
        print(f"  Fields: {list(raw_data.keys())}")

    # ──────────────────────────────────────────────────────
    # STAGE 2: CHUNK
    # ──────────────────────────────────────────────────────
    if "chunked" not in completed_stages:
        print("\n► STAGE 2: Tokenising and chunking...")
        chunks = chunk_data(raw_data, CHUNK_SIZE)
        mark_stage(cp, "chunked", "chunks", chunks)

        with open("output/chunks.json", "w",
                  encoding="utf-8") as f:
            json.dump(chunks, f, indent=2,
                      ensure_ascii=False)
        print(f"  [main] Chunks saved → output/chunks.json")
    else:
        chunks = cp["data"].get("chunks")
        if not chunks:
            chunks = chunk_data(raw_data, CHUNK_SIZE)
        print(f"► STAGE 2: Chunk (cached) ✓  "
              f"({len(chunks)} chunks)")

    # ──────────────────────────────────────────────────────
    # STAGE 3: LLM ENRICHMENT
    # ──────────────────────────────────────────────────────
    if "enriched" not in completed_stages:
        print("\n► STAGE 3: LLM semantic enrichment (Llama 3 8B Prefered)...")
        enriched = enrich_all_chunks(
            chunks, cp, TOKEN_LIMIT)

        if enriched is None:
            print("\n  Pipeline paused mid-enrichment.")
            print("  Re-run `python main.py` when "
                  "OpenRouter quota resets.\n")
            sys.exit(0)

        mark_stage(cp, "enriched", "enriched", enriched)

        with open("output/enriched_data.json", "w",
                  encoding="utf-8") as f:
            json.dump(enriched, f, indent=2,
                      ensure_ascii=False)
        print(f"  [main] Enriched data saved → "
              f"output/enriched_data.json")
    else:
        enriched = cp["data"]["enriched"]
        print(f"► STAGE 3: Enrichment (cached) ✓  "
              f"({len(enriched)} chunks)")

    # ──────────────────────────────────────────────────────
    # STAGE 4: BUILD RDF TRIPLES
    # ──────────────────────────────────────────────────────
    if "triples" not in completed_stages:
        print("\n► STAGE 4: Building RDF triples...")
        g = build_graph(enriched)
        mark_stage(cp, "triples",
                   "triple_count", len(g))
    else:
        print(f"► STAGE 4: Triples (rebuilding from cache)...")
        enriched = cp["data"].get("enriched", enriched)
        g = build_graph(enriched)
        print(f"  (cached triple count was "
              f"{cp['data'].get('triple_count', '?')})")

    # ──────────────────────────────────────────────────────
    # STAGE 5: WRITE OWL FILE
    # ──────────────────────────────────────────────────────
    print("\n► STAGE 5: Writing OWL file...")
    owl_path = save_owl(g, "output/faculty_RC")
    mark_stage(cp, "owl", "owl_path", owl_path)

    # ── Final summary ─────────────────────────────────────
    print(f"\n{'='*58}")
    print(f"  ✅  PIPELINE COMPLETE")
    print(f"{'='*58}")
    print(f"  OWL file   : {owl_path}")
    print(f"  Turtle     : output/faculty_RC.ttl")
    print(f"  Tokens used: {cp['tokens_used']:,} "
          f"/ {TOKEN_LIMIT:,}")
    print(f"\n  Open in Protégé:")
    print(f"    File → Open... → "
          f"{os.path.abspath(owl_path)}")
    print(f"\n  Verify in Protégé:")
    print(f"    Classes tab        → Person, Faculty, "
          f"Publication, etc.")
    print(f"    Object Properties  → hasResearchArea, "
          f"authorOf, etc.")
    print(f"    Data Properties    → fullName, "
          f"emailAddress, etc.")
    print(f"    Individuals tab    → all extracted entities")
    print(f"{'='*58}\n")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        from checkpoint import reset
        reset()
        print("Checkpoint cleared. Run `python main.py` "
              "to start fresh.\n")
    elif "--status" in sys.argv:
        _show_status()
    else:
        run()

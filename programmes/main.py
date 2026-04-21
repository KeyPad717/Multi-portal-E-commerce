    #pipeline orchestrator
import os
import sys
import json
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

def _check_env():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        print("\nERROR: OPENROUTER_API_KEY not set in .env file")
        sys.exit(1)
    urls = os.getenv("TARGET_URLS", "")
    if not urls:
        print("\nERROR: TARGET_URLS not set in .env file (comma separated)\n")
        sys.exit(1)

def run():
    _check_env()

    URLS = [u.strip() for u in os.getenv("TARGET_URLS", "").split(",") if u.strip()]
    TOKEN_LIMIT = int(os.getenv("TOKEN_LIMIT", "12000"))
    CHUNK_SIZE  = int(os.getenv("CHUNK_SIZE", "2000"))

    from checkpoint import load, mark_stage, save, reset
    from scraper import scrape
    from chunker import chunk_data
    from enricher import enrich_all_chunks
    from triple_builder import build_graph
    from owl_writer import save_owl

    print(f"\n{'='*58}")
    print(f"  OWL PIPELINE — IIITB Programmes")
    print(f"{'='*58}")
    print(f"  URLs        : {len(URLS)} detected")
    print(f"{'='*58}\n")

    all_enriched = []
    
    cp = load()

    for i, url in enumerate(URLS):
        # Extract a readable name from the URL
        url_slug = url.strip('/').split('/')[-1].replace('-', '_')
        if not url_slug:
            url_slug = f"programme_{i}"

        print(f"\n\n{'='*58}")
        print(f"  PROCESSING PROGRAMME [{i+1}/{len(URLS)}]: {url_slug}")
        print(f"{'='*58}")
        
        # Scraping
        scraped_file = f"output/scraped_{url_slug}.json"
        if os.path.exists(scraped_file):
            print(f"► STAGE 1: Scrape (cached) ✓")
            with open(scraped_file, "r") as f:
                raw_data = json.load(f)
        else:
            print("► STAGE 1: Scraping webpage...")
            raw_data = scrape(url)
            with open(scraped_file, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2, ensure_ascii=False)
            
        # Chunking
        chunks_file = f"output/chunks_{url_slug}.json"
        if os.path.exists(chunks_file):
            print(f"► STAGE 2: Chunk (cached) ✓")
            with open(chunks_file, "r") as f:
                chunks = json.load(f)
        else:
            print("► STAGE 2: Tokenising and chunking...")
            chunks = chunk_data(raw_data, CHUNK_SIZE)
            with open(chunks_file, "w", encoding="utf-8") as f:
                json.dump(chunks, f, indent=2, ensure_ascii=False)

        # Enriching
        enriched_file = f"output/enriched_{url_slug}.json"
        if os.path.exists(enriched_file):
            print(f"► STAGE 3: Enrichment (cached) ✓")
            with open(enriched_file, "r") as f:
                enriched = json.load(f)
        else:
            print("► STAGE 3: LLM semantic enrichment...")
            # clear partial_enriched for each new url so chunk resuming works properly
            cp["data"]["partial_enriched"] = []
            enriched = enrich_all_chunks(chunks, cp, TOKEN_LIMIT)
            if enriched is None:
                print("\n  Pipeline paused mid-enrichment (Token limit reached).")
                sys.exit(0)
            
            with open(enriched_file, "w", encoding="utf-8") as f:
                json.dump(enriched, f, indent=2, ensure_ascii=False)
                
        all_enriched.extend(enriched)
        
        # separating Triples & OWL
        owl_file = f"output/{url_slug}.owl"
        if not os.path.exists(owl_file):
            print(f"\n► STAGE 4 & 5: Building and writing INDIVIDUAL OWL -> {url_slug}.owl ...")
            g = build_graph(enriched)
            save_owl(g, f"output/{url_slug}")
        else:
            print(f"► STAGE 4 & 5: Individual OWL exists -> {owl_file}")

    print(f"\n\n{'='*58}")
    print(f"  COMBINED PROGRAMMES ONTOLOGY")
    print(f"{'='*58}")
    print("► Building COMBINED RDF triples...")
    g_comb = build_graph(all_enriched)
    comb_owl_path = save_owl(g_comb, "output/programmes_combined")
    print(f"  Created combined ontology -> {comb_owl_path}")

    print(f"\n  Final tokens used: {cp.get('tokens_used', 0)}")
    print(f"{'='*58}\n")

if __name__ == "__main__":
    if "--reset" in sys.argv:
        from checkpoint import reset
        reset()
        print("Checkpoint cleared. Delete files in output/ to cleanly restart everything.")
    else:
        run()

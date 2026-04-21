"""
verify.py — Quick sanity checks before running the full pipeline.
Tests: package imports, API key validity, URL reachability,
       scraper output, chunker output.
Does NOT call the LLM — safe to run anytime.

Usage:
    python verify.py
"""

import sys
import os

print("\n" + "="*55)
print("  PIPELINE VERIFICATION")
print("="*55)

# ── 1. Check .env ─────────────────────────────────────────
print("\n[1] Checking .env ...")
try:
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("OPENROUTER_API_KEY", "")
    url = os.getenv("TARGET_URL", "")
    if not key or "your_google" in key:
        print("  ❌  GEMINI_API_KEY not set in .env")
        print("      Get key: https://aistudio.google.com/app/apikey")
        sys.exit(1)
    print(f"  ✓  GEMINI_API_KEY: {key[:8]}...")
    print(f"  ✓  TARGET_URL: {url}")
    print(f"  ✓  TOKEN_LIMIT: {os.getenv('TOKEN_LIMIT', '12000')}")
except Exception as e:
    print(f"  ❌  {e}")
    sys.exit(1)

# ── 2. Check package imports ──────────────────────────────
print("\n[2] Checking required packages ...")
packages = [
    ("requests",              "requests"),
    ("bs4",                   "beautifulsoup4"),
    ("lxml",                  "lxml"),
    ("rdflib",                "rdflib"),
    ("tiktoken",              "tiktoken"),
    ("google.generativeai",   "google-generativeai"),
    ("dotenv",                "python-dotenv"),
]
all_ok = True
for mod, pkg in packages:
    try:
        __import__(mod)
        print(f"  ✓  {pkg}")
    except ImportError:
        print(f"  ❌  {pkg} not installed → "
              f"pip install {pkg}")
        all_ok = False
if not all_ok:
    print("\n  Run: pip install -r requirements.txt")
    sys.exit(1)

# ── 3. Test URL reachability ──────────────────────────────
print(f"\n[3] Testing URL reachability ...")
try:
    import requests as req
    r = req.get(url, timeout=10,
                headers={"User-Agent": "Mozilla/5.0"})
    print(f"  ✓  HTTP {r.status_code} — "
          f"{len(r.text):,} bytes received")
except Exception as e:
    print(f"  ❌  Cannot reach URL: {e}")
    sys.exit(1)

# ── 4. Test scraper ───────────────────────────────────────
print(f"\n[4] Running scraper ...")
try:
    from scraper import scrape
    data = scrape(url)
    for field, value in data.items():
        if field in ["url", "raw_sections"]:
            continue
        if isinstance(value, list):
            print(f"  ✓  {field}: {len(value)} items")
        else:
            preview = str(value)[:60]
            print(f"  ✓  {field}: {preview}")
except Exception as e:
    print(f"  ❌  Scraper error: {e}")
    sys.exit(1)

# ── 5. Test chunker ───────────────────────────────────────
print(f"\n[5] Running chunker ...")
try:
    from chunker import chunk_data, estimate_json_tokens
    chunks = chunk_data(data,
                        int(os.getenv("CHUNK_SIZE", "2000")))
    total_tok = sum(estimate_json_tokens(c) for c in chunks)
    print(f"  ✓  {len(chunks)} chunk(s), "
          f"~{total_tok} tokens total")
except Exception as e:
    print(f"  ❌  Chunker error: {e}")
    sys.exit(1)

# ── 6. Test Gemini API connection (lightweight) ───────────
print(f"\n[6] Testing LLM API connection ...")
try:
    from openai import OpenAI
    import os

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    response = client.chat.completions.create(
        model="meta-llama/llama-3-8b-instruct",
        messages=[{"role": "user", "content": "Reply with: OK"}],
    )

    answer = response.choices[0].message.content.strip()
    print(f"  ✓  Model responded: '{answer}'")

except Exception as e:
    print(f"  ❌  LLM API error: {e}")
    sys.exit(1)

print(f"\n{'='*55}")
print(f"  ✅  ALL CHECKS PASSED — ready to run pipeline!")
print(f"      Run: python main.py")
print(f"{'='*55}\n")

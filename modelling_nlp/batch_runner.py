import sys
import time
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper import scrape_text_from_url
from extractor import extract_triples
from owl_generator import generate_owl
from master_schema import OntologyData

def filter_url(url: str) -> bool:
    """Returns True if the URL should be processed, False to skip."""
    url = url.lower()
    
    # 1. Skip non-scrapable files
    if any(url.endswith(ext) for ext in [".pdf", ".jpg", ".png", ".jpeg", ".mp4", ".zip", ".gz"]):
        return False
        
    # 2. Skip user-requested avoid sections (e.g. news)
    skip_keywords = ["/news/", "/events/", "/media-press-releases", "wp-content/uploads", "in-the-press"]
    if any(kwd in url for kwd in skip_keywords):
        return False
        
    return True

def process_single_url(url: str):
    print(f"[{url}] Scraping...")
    # Scrape
    text = scrape_text_from_url(url)
    if not text or len(text) < 50:
        return url, []

    print(f"[{url}] Extracted {len(text)} chars. Calling LLM (this may take a moment)...")
    
    # Simple backoff to avoid rate-limits
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # We enforce a small sleep between chunks to help with rate limits on Groq
            time.sleep(2)
            data = extract_triples(text)
            
            # extract_triples returns empty if it fails. If we hit rate limit, it likely logs inside extractor
            if data and len(data.triples) > 0:
                print(f"[{url}] Got {len(data.triples)} triples.")
                return url, [t.dict() for t in data.triples]
            else:
                return url, []
        except Exception as e:
            print(f"[{url}] Attempt {attempt+1} failed: {e}")
            time.sleep(5 * (attempt + 1))
            
    return url, []

def main():
    urls_file = "unique_urls.txt"
    checkpoint_file = "data.json"
    
    if not os.path.exists(urls_file):
        print(f"File {urls_file} not found!")
        sys.exit(1)
        
    # Load all URLs
    with open(urls_file, "r") as f:
        all_urls = [line.strip() for line in f if line.strip()]
        
    # Filter
    filtered_urls = [u for u in all_urls if filter_url(u)]
    print(f"Loaded {len(all_urls)} URLs. After filtering, {len(filtered_urls)} remain to be processed.")

    # Load from checkpoint if exists
    cumulative_data = {}
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
             cumulative_data = json.load(f)
        print(f"Resuming from checkpoint: {len(cumulative_data)} URLs already processed.")

    urls_to_process = [u for u in filtered_urls if u not in cumulative_data]
    print(f"Actually processing {len(urls_to_process)} URLs in this run.")
    
    # We use a ThreadPool but low parallelism to avoid immediate HTTP 429 from Groq
    max_workers = 3
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(process_single_url, url): url for url in urls_to_process}
        
        for i, future in enumerate(as_completed(future_to_url)):
            url = future_to_url[future]
            try:
                processed_url, triples = future.result()
                cumulative_data[processed_url] = triples
            except Exception as exc:
                print(f"URL processing {url} generated an exception: {exc}")
                cumulative_data[url] = []
                
            # Checkpoint every 5 URLs completed
            if i % 5 == 0:
                with open(checkpoint_file, "w") as f:
                    json.dump(cumulative_data, f, indent=2)
                    
    # Final checkpoint save
    with open(checkpoint_file, "w") as f:
        json.dump(cumulative_data, f, indent=2)
        
    print("\n--- Processing Complete ---")
    
    # Reassemble Ontology Data for OWL generation
    print("Compiling all triples and deduplicating...")
    from master_schema import Triple
    
    unique_triples = set()
    final_triples_list = []
    
    for url, t_list in cumulative_data.items():
        for t in t_list:
            # simple tuple string hash for deduplication
            signature = f"{t['subject']}|{t['predicate']}|{t['object']}"
            if signature not in unique_triples:
                unique_triples.add(signature)
                final_triples_list.append(Triple(**t))
                
    if final_triples_list:
        print(f"Total unique triples extracted: {len(final_triples_list)}")
        big_ontology = OntologyData(triples=final_triples_list)
        generate_owl(big_ontology, "iiitb_massive_ontology.owl")
    else:
        print("No triples extracted from the run.")

if __name__ == "__main__":
    main()

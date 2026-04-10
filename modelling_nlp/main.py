import argparse
import sys
from scraper import scrape_text_from_url
from extractor import extract_triples
from owl_generator import generate_owl

def main():
    parser = argparse.ArgumentParser(description="Run the automated Ontology Generation Pipeline")
    parser.add_argument("--url", type=str, default="https://www.iiitb.ac.in/faculty", help="Target URL to crawl")
    parser.add_argument("--output", type=str, default="iiitb_ontology.owl", help="Output OWL file name")
    
    args = parser.parse_args()
    
    print(f"Starting Pipeline for URL: {args.url}")
    
    # Scraping
    print("\n[1/4] Scraping text data...")
    raw_text = scrape_text_from_url(args.url)
    if not raw_text:
        print("Failed to extract any text. Exiting.")
        sys.exit(1)
        
    print(f"-> Extracted {len(raw_text)} characters.")
    
    # LLM Extraction
    print("\n[2/4] Sending text to Groq LLM for triple extraction...")
    ontology_data = extract_triples(raw_text)
    
    if not ontology_data or len(ontology_data.triples) == 0:
        print("Model failed to extract any triples conforming to the schema.")
        sys.exit(1)
        
    print(f"-> Extracted {len(ontology_data.triples)} triples successfully.")
    for i, triple in enumerate(ontology_data.triples):
        print(f"   {i+1}. {triple.subject} -> {triple.predicate} -> {triple.object}")
        
    # Generating OWL
    print(f"\n[3/4] Generating OWL representation: {args.output}...")
    generate_owl(ontology_data, args.output)
    
    print("\n[4/4] Pipeline Complete!")
    print(f"Check the file '{args.output}'")

if __name__ == "__main__":
    main()

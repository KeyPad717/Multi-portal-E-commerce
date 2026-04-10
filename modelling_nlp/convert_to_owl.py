import json
from master_schema import Triple, OntologyData
from owl_generator import generate_owl

def convert_json_to_owl(input_json="data.json", output_owl="iiitb_massive_ontology.owl"):
    # Load the scraped data
    with open(input_json, "r") as f:
        cumulative_data = json.load(f)
        
    print(f"Loaded data for {len(cumulative_data)} URLs.")
    
    unique_triples = set()
    final_triples_list = []
    
    # Flatten and deduplicate
    for url, triples_list in cumulative_data.items():
        for t in triples_list:
            signature = f"{t['subject']}|{t['predicate']}|{t['object']}"
            if signature not in unique_triples:
                unique_triples.add(signature)
                final_triples_list.append(Triple(**t))
                
    if final_triples_list:
        print(f"Total unique triples to generate: {len(final_triples_list)}")
        big_ontology = OntologyData(triples=final_triples_list)
        generate_owl(big_ontology, output_owl)
    else:
        print("No triples found in data.json!")

if __name__ == "__main__":
    convert_json_to_owl()

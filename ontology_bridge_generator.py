import os
import json
import time
from openai import OpenAI
from dotenv import load_dotenv

# Load API Key
load_dotenv(dotenv_path="/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/programmes/.env")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

MODEL = "meta-llama/llama-3-70b-instruct"

BRIDGE_PROMPT = """You are an expert ontology integration engineer.
Your task is to identify semantic links between two different institutional ontologies.

SYSTEM A (Departments):
{dept_signature}

SYSTEM B (Programmes):
{prog_signature}

GOAL:
Generate a set of OWL/RDF triples that bridge these two systems.
1. Use owl:equivalentClass for classes that represent the exact same concept.
2. Use owl:equivalentProperty for ObjectProperties and DatatypeProperties. 
   - REASONING: Compare property labels, but prioritize the 'domain', 'range', and 'examples' provided in the signature.
   - If two properties connect the same or equivalent classes and have similar sample values, they are likely equivalent.
3. Use owl:sameAs for individuals that represent the exact same entity.
4. Create custom ObjectProperties to link Programmes to Departments (e.g. onto:managedBy).
5. Identify which Programmes belong to which Departments based on titles (CSE vs ECE).

NAMESPACES:
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:owl="http://www.w3.org/2002/07/owl#"
    xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
    xmlns:cse="https://cse.iiitb.ac.in#"
    xmlns:ece="https://ece.iiitb.ac.in#"
    xmlns:dept="http://iiitb.ac.in/ontology/departments#"
    xmlns:prog="http://iiitb.ac.in/ontology/programmes#"
    xmlns:bridge="http://iiitb.ac.in/ontology/bridge#"

OUTPUT REQUIREMENTS:
Return ONLY a valid RDF/XML block inside <rdf:RDF> tags. 
No other explanations.
"""

def generate_bridge():
    # Load signatures
    sig_path = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/bridge_signatures.json"
    with open(sig_path, "r") as f:
        signatures = json.load(f)

    prompt = BRIDGE_PROMPT.format(
        dept_signature=json.dumps(signatures["departments"], indent=2),
        prog_signature=json.dumps(signatures["programmes"], indent=2)
    )

    print("🚀 Sending signatures to Llama 3 70B for bridge reasoning...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": "You are a professional ontologist."},
                      {"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.0
        )

        raw_output = response.choices[0].message.content.strip()
        
        # Extract XML
        import re
        match = re.search(r"<rdf:RDF.*?</rdf:RDF>", raw_output, re.DOTALL | re.IGNORECASE)
        if match:
            bridge_xml = match.group()
            output_path = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/bridge_axioms.owl"
            with open(output_path, "w") as f:
                f.write(bridge_xml)
            print(f"✅ Bridge axioms generated at {output_path}")
        else:
            print("❌ Failed to extract RDF/XML from LLM output.")
            print(f"Raw Output start: {raw_output[:200]}")

    except Exception as e:
        print(f"❌ Error calling LLM: {e}")

if __name__ == "__main__":
    generate_bridge()

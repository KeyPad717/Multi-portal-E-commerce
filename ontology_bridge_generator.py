import os
import sys
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

MODEL = "meta-llama/llama-3.1-70b-instruct"

BRIDGE_PROMPT = """You are an expert ontology integration engineer.
Your task is to identify semantic links between two different institutional ontologies.

SYSTEM A (Departments Raw OWL):
{dept_content}

SYSTEM B (Programmes Raw OWL):
{prog_content}

GOAL:
Generate a set of OWL/RDF triples that bridge these two systems.
1. Use owl:equivalentClass for classes that represent the exact same concept.
2. Use owl:equivalentProperty for ObjectProperties and DatatypeProperties. 
3. Use owl:sameAs for individuals that represent the exact same entity.
4. Create custom ObjectProperties to link Programmes to Departments (e.g. bridge:managedBy).
5. Identify which Programmes belong to which Departments based on content.

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
Return ONLY a valid Turtle block (TTL). 
Use standard prefixes.
No explanations.
"""

def generate_bridge():
    # Load raw content instead of signatures
    dept_path = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/departments/departments_combined.owl"
    prog_path = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/programmes/output/programmes_combined.owl"
    
    with open(dept_path, "r") as f:
        dept_content = f.read()
    with open(prog_path, "r") as f:
        prog_content = f.read()

    prompt = BRIDGE_PROMPT.format(
        dept_content=dept_content,
        prog_content=prog_content
    )

    print(f"PROCEEDING Sending full OWL files (~{len(dept_content)+len(prog_content)} chars) to Llama 3 for bridge reasoning...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": "You are a professional ontologist. Always output valid Turtle."},
                      {"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.0
        )

        message = response.choices[0].message
        raw_output = message.content
        
        if raw_output is None:
            print("ERROR LLM returned empty content. Possible refusal or error.")
            print(f"Full response message: {message}")
            sys.exit(1)
        
        raw_output = raw_output.strip()
        
        # Extract Turtle using a more robust regex or by looking for code blocks
        import re
        turtle_match = re.search(r"```(?:turtle|ttl)?\s*(.*?)\s*```", raw_output, re.DOTALL | re.IGNORECASE)
        if turtle_match:
            turtle_code = turtle_match.group(1)
        else:
            # Fallback to taking everything if no code blocks are used
            turtle_code = raw_output

        # Validate and Convert to RDF/XML for the builder
        from rdflib import Graph
        g = Graph()
        try:
            g.parse(data=turtle_code, format="turtle")
            output_path = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/bridge_axioms.owl"
            g.serialize(destination=output_path, format="pretty-xml")
            print(f"DONE Bridge axioms generated and validated at {output_path}")
        except Exception as parse_err:
            print(f"ERROR Failed to parse LLM output: {parse_err}")
            print(f"--- RAW OUTPUT START ---")
            print(raw_output)
            print(f"--- RAW OUTPUT END ---")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR Error calling LLM: {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_bridge()

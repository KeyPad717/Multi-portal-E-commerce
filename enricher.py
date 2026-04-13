import os
import json
import time
import re
from openai import OpenAI
from chunker import count_tokens

# ── Configure OpenRouter ────────────────────────────────
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# UPGRADED to 70B for high-fidelity semantic induction
MODEL = "meta-llama/llama-3-70b-instruct"


SYSTEM_PROMPT = """You are an autonomous ontology engineer.

Your task is to construct a complete OWL ontology from extracted data.

The ontology must be fully emergent.
No predefined schema, template, or ontology structure may be assumed.

All classes, individuals, and relationships must be invented purely from semantic understanding of the data.

Core Principles:
1. Everything must emerge from the input data.
2. Do not assume any predefined ontology structure or common class hierarchies (no 'Person', 'Faculty', etc.).
3. Prefer semantic meaning over structural regularity. 
4. Prefer entities over literals when meaningful.
5. Infer relationships even when implicit from context or structure.
6. Create abstractions when conceptually useful (roles, groups, functional categories).
7. Allow conceptual classes even if few instances exist.
8. Focus on semantic correctness rather than syntactic clustering.

Ontology Construction Guidelines:
- Entity Modeling: Identify meaningful entities; convert literals to entities when they represent reusable concepts.
- Class Induction: Create classes when entities share semantic roles. Infer subclass relationships when appropriate.
- Relationship Induction: Create ObjectProperties between entities and DatatypeProperties for literals. Create inverse relationships when natural. Infer domain and range.
- Hierarchy Construction: Infer containment, membership, and specialization relationships.
- Semantic Enrichment: Use OWL constructs (subClassOf, inverseOf, Restriction). Add rdfs:comment annotations describing semantics.

Schema.org Alignment (Optional):
After constructing the ontology, you may align with schema.org via owl:equivalentClass/Property or reuse URIs, but do NOT replace the emergent structure.

Output Requirements:
Return ONLY a valid OWL ontology in RDF/XML format.
Include standard namespaces:
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:owl="http://www.w3.org/2002/07/owl#"
    xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
    xmlns:onto="http://iiitb.ac.in/ontology/autonomous#"

CRITICAL XML RULES:
1. Every individual or class MUST be defined in a single block.
2. Do NOT use the same rdf:ID twice.
3. Use rdf:resource and NOT resource. Use rdf:about and NOT about.
4. Correct structure for individuals:
   <owl:NamedIndividual rdf:ID="EntityID">
     <rdf:type rdf:resource="#ClassName"/>
     <onto:property rdf:resource="#OtherEntity"/>
     <onto:dataProperty rdf:datatype="xsd:string">Value</onto:dataProperty>
   </owl:NamedIndividual>
5. ESCAPE all special characters in text (e.g., use &amp; for &).

Do not include explanations, reasoning steps, or phase outputs.
Only the final RDF/XML.
"""



# ── Extract RDF/XML safely ───────────────────────────────
def sanitize_xml_block(xml_text):
    # Escape ampersands that aren't already part of an entity
    xml_text = re.sub(r"&(?!(?:amp|lt|gt|quot|apos);)", "&amp;", xml_text)
    return xml_text

def extract_rdfxml(text):
    try:
        # Search for the LAST <rdf:RDF> block
        matches = list(re.finditer(r"<rdf:RDF.*?</rdf:RDF>", text, re.DOTALL | re.IGNORECASE))
        if matches:
            block = matches[-1].group()
            return sanitize_xml_block(block)
        
        # Fallback to <owl:Ontology if that's all there is
        matches = list(re.finditer(r"<owl:Ontology.*?</owl:Ontology>", text, re.DOTALL | re.IGNORECASE))
        if matches:
            snippet = matches[-1].group()
            if 'xmlns:rdf=' not in snippet:
                header = '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" ' \
                         'xmlns:owl="http://www.w3.org/2002/07/owl#" ' \
                         'xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" ' \
                         'xmlns:xsd="http://www.w3.org/2001/XMLSchema#">\n'
                snippet = header + snippet + '\n</rdf:RDF>'
            return sanitize_xml_block(snippet)
    except:
        pass
    return None


# ── LLM Call ────────────────────────────────────────────
def call_llm(prompt, retries=3):
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.0
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"    [enricher] API error (attempt {attempt+1}/{retries}): {e}")
            time.sleep(2 * (attempt + 1))

    return None


# ── Enrich single chunk ─────────────────────────────────
def enrich_chunk(chunk, cp, token_limit):

    clean_text = f"""
    Name: {chunk.get("name", "")}
    Title: {chunk.get("title", "")}
    Bio: {chunk.get("bio", "")}
    Sections: {chunk.get("raw_sections", "")}
    """

    prompt = SYSTEM_PROMPT + "\n\nINPUT DATA:\n" + clean_text

    tokens = count_tokens(prompt)

    from checkpoint import check_token_budget
    if not check_token_budget(cp, tokens * 2, token_limit):
        return None

    print(f"    [enricher] Sending ~{tokens} tokens to Autonomous Engineer (70B)...")

    raw = call_llm(prompt)

    if raw is None:
        return {
            "error": "LLM failed",
            "raw_output": ""
        }

    # Extract RDF/XML 
    result = extract_rdfxml(raw)

    if result:
        print(f"    [enricher] ✓ Semantic RDF/XML extracted ({len(result)} chars)")
        return result
    else:
        print("    [enricher] ⚠ RDF/XML extraction failed")
        print(f"    [debug] Raw output start: {raw[:100]}...")

        return {
            "error": "Extraction failed",
            "raw_output": raw
        }


# ── Enrich all chunks ───────────────────────────────────
def enrich_all_chunks(chunks, cp, token_limit):

    results = list(cp["data"].get("partial_enriched", []))
    start_idx = len(results)

    if start_idx > 0:
        print(f"  [enricher] Resuming from chunk {start_idx+1}/{len(chunks)}")

    for i, chunk in enumerate(chunks[start_idx:], start=start_idx):

        print(f"\n  [enricher] ── Chunk {i+1}/{len(chunks)} ──")

        enriched = enrich_chunk(chunk, cp, token_limit)

        if enriched is None:
            cp["data"]["partial_enriched"] = results
            cp["data"]["chunks"] = chunks
            from checkpoint import save
            save(cp)
            return None

        results.append(enriched)
        cp["data"]["partial_enriched"] = results
        from checkpoint import save
        save(cp)
        time.sleep(1)

    return results

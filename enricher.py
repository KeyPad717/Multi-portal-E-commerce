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

MODEL = "meta-llama/llama-3-8b-instruct"
# You can also try:
# MODEL = "nousresearch/nous-hermes-2-mistral-7b-dpo"


SYSTEM_PROMPT = """You are an autonomous ontology engineer.

Your task is to construct a complete OWL ontology from the provided extracted data.

You must NOT rely on any predefined schema. All classes, individuals, and relationships must be invented purely from your own reasoning based on the input data.

Phase 1 — Emergent Ontology Construction (No external schema)

1. Analyze the input data.
2. Invent classes dynamically.
3. Invent object properties dynamically.
4. Invent datatype properties dynamically.
5. Create individuals when appropriate.
6. Prefer modeling meaningful concepts as entities rather than literals.
7. Create relationships purely from semantic understanding of the data.
8. Infer class hierarchies when meaningful.
9. Infer domain and range when appropriate.
10. Create inverse relationships when they naturally exist and add value.
11. Add rdfs:comment annotations describing semantics.
12. Use OWL constructs where appropriate (subClassOf, inverseOf, etc.)

Phase 2 — Optional Schema.org Verification

After constructing the ontology:
1. Review the relationships and classes you created.
2. Check whether any of them align with schema.org concepts.
3. If alignment exists, you may declare equivalence or add supplemental semantics.
4. Do NOT replace your ontology structure — only enrich or align.

Constraints
- Do NOT hallucinate hundreds of properties. Focus on quality over quantity.
- Do NOT use blank node syntax `[ ... ]`. Every entity must be a named individual with its own ID (e.g. `onto:EntityName`).
- Do NOT copy known ontology structures.
- Everything must be derived from the provided data.

Output Requirements
Produce a valid OWL ontology in Turtle (N3) format.

IMPORTANT: Your response MUST be EXACTLY a valid Turtle document.
- Start with prefix declarations:
    @prefix onto: <http://iiitb.ac.in/ontology/autonomous#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
- Use standard Turtle syntax: [Subject] [Predicate] [Object] .
- EVERY TRIPLE must end with a dot `.` followed by a newline.
- NEVER use shared objects with semicolons or commas; write each triple fully for maximum stability.
- Example: onto:Professor rdf:type owl:Class .
- Example: onto:Professor rdfs:comment "A faculty member." .
- Do NOT include any conversational preamble or markdown backticks.
"""



# ── Extract Turtle safely ───────────────────────────────
def extract_turtle(text):
    try:
        # Step 1: Clean markdown backticks
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                if "@prefix" in part or "onto:" in part:
                     text = part
                     if text.strip().startswith("turtle") or text.strip().startswith("n3"):
                         text = "\n".join(text.split("\n")[1:])
                     break

        lines = text.strip().split("\n")
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Handle prefix lines
            if line.startswith("@prefix"):
                if not line.endswith("."):
                    line += " ."
                cleaned_lines.append(line)
                continue

            # Handle triples (very basic repair)
            # If line doesn't end with a dot/comma/semicolon, add a dot
            if not line.endswith(".") and not line.endswith(";") and not line.endswith(","):
                line += " ."
            
            cleaned_lines.append(line)
        
        final_text = "\n".join(cleaned_lines)
        
        # Step 3: Find the actual start
        start = final_text.find("@prefix")
        if start != -1:
            return final_text[start:].strip()
        
        return final_text.strip()
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

    print(f"    [enricher] Sending ~{tokens} tokens to OpenRouter...")

    raw = call_llm(prompt)

    if raw is None:
        return {
            "error": "LLM failed",
            "raw_output": ""
        }

    # Extract Turtle safely
    result = extract_turtle(raw)

    if result:
        print(f"    [enricher] ✓ Turtle extracted ({len(result)} chars)")
        return result
    else:
        print("    [enricher] ⚠ Turtle extraction failed")
        print(f"    [debug] Raw start: {raw[:100]}...")

        return {
            "error": "Turtle extraction failed",
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

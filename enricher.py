import os
import json
import time
import re
from openai import OpenAI
from chunker import count_tokens

# ── Configure OpenRouter ──────────────────────────────────
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

MODEL = "meta-llama/llama-3-8b-instruct"
# You can also try:
# MODEL = "nousresearch/nous-hermes-2-mistral-7b-dpo"


# ── STRICT PROMPT (VERY IMPORTANT) ──────────────────────
SYSTEM_PROMPT = """You are an expert in knowledge graph construction and ontology engineering.

Extract ALL possible structured knowledge from the given faculty profile.

STRICT RULES:
- Return ONLY valid JSON
- No explanation, no markdown, no extra text
- Be exhaustive — do NOT return minimal output

Extract:

1. PERSON
- Name
- Role (Professor, Researcher, etc.)

2. ORGANIZATION
- University, labs, institutes

3. RESEARCH AREAS
- All topics mentioned

4. PUBLICATIONS (if present)

5. CONCEPTS / SKILLS

RELATIONSHIPS (very important):
- worksAt
- hasResearchArea
- authorOf
- relatedTo

Convert sentences into triples:
Example:
"works in data mining" → Person → hasResearchArea → Data Mining

OUTPUT FORMAT:

{
  "entities": [
    {
      "id": "unique_id",
      "type": "Person|Organization|ResearchArea|Publication|Concept",
      "label": "name",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "subject_id": "",
      "predicate": "",
      "object_id": "",
      "object_type": "entity|literal"
    }
  ],
  "owl_annotations": {
    "domain_hints": {},
    "range_hints": {},
    "inverse_of": {},
    "functional_properties": [],
    "symmetric_properties": []
  }
}
"""


# ── Extract JSON safely ─────────────────────────────────
def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
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
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"    [enricher] API error (attempt {attempt+1}/{retries}): {e}")
            time.sleep(2 * (attempt + 1))

    return None


# ── Enrich single chunk ─────────────────────────────────
def enrich_chunk(chunk, cp, token_limit):

    chunk_json = json.dumps(chunk, indent=2, ensure_ascii=False)
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
        print("    [enricher] ⚠ Critical API failure or rate limit hit. Pausing pipeline to prevent data loss.")
        return None

    # Clean markdown
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    if raw.startswith("json"):
        raw = raw[4:].strip()

    # Extract JSON safely
    result = extract_json(raw)

    if result:
        entities = result.get("entities", [])
        rels = result.get("relationships", [])
        print(f"    [enricher] ✓ {len(entities)} entities, {len(rels)} relationships")
        return result
    else:
        print("    [enricher] ⚠ JSON parse failed")

        return {
            "entities": [],
            "relationships": [],
            "owl_annotations": {},
            "raw_output": raw[:500]
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

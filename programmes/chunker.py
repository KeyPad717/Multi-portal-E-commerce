"""
chunker.py -- Token counting and data chunking.
Splits scraped JSON into token-bounded chunks so each
LLM call stays within rate limits while preserving context.
"""

import json
import tiktoken

# cl100k is the encoding used by GPT-4 / Gemini approximation
enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string."""
    return len(enc.encode(str(text)))


def estimate_json_tokens(obj) -> int:
    """Estimate tokens for a JSON-serialised object."""
    return count_tokens(json.dumps(obj, ensure_ascii=False))


def chunk_data(data: dict, chunk_token_limit: int = 2000) -> list:
    """
    Split the scraped data dict into a list of smaller dicts,
    each within chunk_token_limit tokens.
    Priority ordering ensures the most semantically rich
    fields are processed first and never split mid-item.
    """
    # Process in priority order (richest first)
    priority_order = [
        "name", "title", "department", "email", "phone",
        "bio", "research_areas", "education",
        "publications", "projects", "awards",
        "courses", "students", "professional_activities",
        "raw_sections"
    ]

    # Collect keys in priority order, then any remaining
    ordered_keys = [k for k in priority_order if k in data]
    remaining = [k for k in data if k not in priority_order
                 and k != "url"]
    ordered_keys += remaining

    chunks = []
    current_chunk = {"url": data.get("url", "")}
    current_tokens = estimate_json_tokens(current_chunk)

    for key in ordered_keys:
        value = data[key]
        field_tokens = estimate_json_tokens({key: value})

        # If a single list field is too large, split it
        if isinstance(value, list) and \
                field_tokens > chunk_token_limit:
            for item in value:
                item_tokens = estimate_json_tokens(
                    {key: [item]})
                if current_tokens + item_tokens > \
                        chunk_token_limit and \
                        len(current_chunk) > 1:
                    chunks.append(current_chunk)
                    current_chunk = {"url": data.get("url", "")}
                    current_tokens = estimate_json_tokens(
                        current_chunk)
                current_chunk.setdefault(key, []).append(item)
                current_tokens += item_tokens
        else:
            if current_tokens + field_tokens > \
                    chunk_token_limit and \
                    len(current_chunk) > 1:
                chunks.append(current_chunk)
                current_chunk = {"url": data.get("url", "")}
                current_tokens = estimate_json_tokens(
                    current_chunk)
            current_chunk[key] = value
            current_tokens += field_tokens

    if len(current_chunk) > 1:
        chunks.append(current_chunk)

    total_tokens = sum(estimate_json_tokens(c)
                       for c in chunks)
    print(f"  [chunker] ✓ {len(chunks)} chunk(s) created, "
          f"~{total_tokens} tokens total")
    for i, c in enumerate(chunks):
        keys_in_chunk = [k for k in c if k != "url"]
        print(f"    Chunk {i+1}: {keys_in_chunk} "
              f"(~{estimate_json_tokens(c)} tokens)")
    return chunks

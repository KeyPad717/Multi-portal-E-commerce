
import requests
from bs4 import BeautifulSoup
import json
import time
import re
import os
import sys
import signal
import urllib.parse
import urllib3
from groq import Groq
from rdflib import Graph, Literal, RDF, RDFS, OWL, URIRef, Namespace, XSD
from pydantic import BaseModel, Field
from typing import List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()


#  CONFIG  — only things you should ever need to change

TARGET_URL   = "https://ece.iiitb.ac.in/"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"

# Token safety
SECTION_DELAY       = 3    # seconds between Groq calls
RATE_LIMIT_PAUSE    = 90   # seconds to wait on 429 / quota error
MAX_RETRIES         = 3    # attempts per section before giving up
MAX_CHARS_PER_SEC   = 4000 # hard cap on text sent per LLM call
MAX_TRIPLES_PER_SEC = 25   # max triples to request per section

# Scraper quality
MIN_SECTION_CHARS = 80     # skip sections shorter than this

# ── Derive everything else from TARGET_URL — nothing else is hardcoded ──
_parsed      = urllib.parse.urlparse(TARGET_URL)
_domain_slug = re.sub(r'[^a-z0-9]', '_', _parsed.netloc.lower()).strip('_')

CHECKPOINT_FILE = f"{_domain_slug}_checkpoint_V2.json"
RAW_JSON_FILE   = f"{_domain_slug}_extracted_raw_V2.json"
TRIPLES_FILE    = f"{_domain_slug}_triples_V2.json"
OWL_FILE        = f"{_domain_slug}_ontology_V2.owl"
ONT_NS          = f"{TARGET_URL.rstrip('/')}#"
ONT_PREFIX      = _domain_slug[:8]   # short prefix for Turtle serialisation


#  PYDANTIC SCHEMA  — fully open, LLM decides all type names

class EnrichedTriple(BaseModel):
    subject: str = Field(
        description=(
            "The source named entity — a person, programme, lab, concept, "
            "or any real-world thing. Keep it a concise noun phrase."
        )
    )
    predicate: str = Field(
        description=(
            "A camelCase verb phrase describing the relationship, e.g. "
            "teachesCourse, conductsResearchIn, isPartOf, offersProgram, "
            "collaboratesWith, supervisesStudent, receivedAward, locatedIn. "
            "Invent whatever predicate best captures the relationship — do NOT "
            "limit yourself to any fixed list."
        )
    )
    object: str = Field(
        description=(
            "The target entity or literal value. Keep it a concise noun phrase "
            "or short string."
        )
    )
    subject_type: str = Field(
        description=(
            "The most specific OWL class name that describes the subject. "
            "Invent a meaningful PascalCase class name based on what the entity "
            "actually is — e.g. AssistantProfessor, PhDScholar, VLSILab, "
            "MTechProgramme, ResearchGroup, JournalPublication, InternationalConference. "
            "Do NOT restrict yourself to any predefined list."
        )
    )
    object_type: str = Field(
        description=(
            "The most specific OWL class name that describes the object. "
            "Use 'Literal' only when the object is a plain data value "
            "(a number, a year, a percentage, a short descriptive string). "
            "Otherwise invent a meaningful PascalCase class name."
        )
    )
    confidence: float = Field(
        description=(
            "Your confidence that this triple is factually correct, from 0.0 to 1.0. "
            "Be strict — only assign above 0.8 for clearly stated facts."
        )
    )
    source_section: str = Field(
        description="The heading of the page section this triple was extracted from."
    )

class OntologyData(BaseModel):
    triples: List[EnrichedTriple] = Field(
        description="All enriched semantic triples extracted from this section."
    )



#  For shutdown — Ctrl+C saves and exits cleanly

_shutdown_requested = False

def _handle_sigint(sig, frame):
    global _shutdown_requested
    print("\n\n  Interrupt received — finishing current section then saving…")
    _shutdown_requested = True

signal.signal(signal.SIGINT, _handle_sigint)



#  CHECKPOINT HELPERS

def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f" Checkpoint loaded — {len(data.get('processed_sections', []))} sections already done.")
        return data
    return {"processed_sections": [], "triples": []}

def save_checkpoint(checkpoint: dict):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)

def save_triples_json(triples: list):
    with open(TRIPLES_FILE, "w", encoding="utf-8") as f:
        json.dump(triples, f, indent=2, ensure_ascii=False)



#  Seq. 1 — SCRAPE & STRUCTURE THE TARGET PAGE

def scrape_single_page(url: str) -> dict:
    """
    Deeply scrapes one page, organises content by heading hierarchy.
    Returns dict: section_key -> {title, clean_text, char_count}
    """
    print(f"\n Scraping: {url}")
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    retry_strategy = Retry(
        total=5, connect=5, read=5,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    session.mount("http://",  HTTPAdapter(max_retries=retry_strategy))
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    resp = None
    for attempt_url in [url, url.replace("http://", "https://")]:
        try:
            resp = session.get(attempt_url, headers=headers,
                               timeout=(30, 120), allow_redirects=True, verify=False)
            resp.raise_for_status()
            print(f"    Fetched: {attempt_url}")
            break
        except Exception as e:
            print(f"     {attempt_url} → {e}")

    if resp is None:
        print("Could not fetch the page. Exiting.")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "lxml")

    # Strip boilerplate — everything that is not content
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "noscript", "iframe", "form", "button"]):
        tag.decompose()

    # Heading-driven section extraction 
    sections      = {}
    current_key   = "overview"
    current_title = "Overview"
    current_buf   = []

    def flush_section():
        if not current_buf:
            return
        raw   = " ".join(current_buf)
        clean = re.sub(r'\s+', ' ', raw).strip()
        if len(clean) >= MIN_SECTION_CHARS:
            sections[current_key] = {
                "title":      current_title,
                "clean_text": clean[:MAX_CHARS_PER_SEC],
                "char_count": len(clean)
            }

    heading_tags = {"h1", "h2", "h3", "h4", "h5"}

    for el in soup.find_all(["h1","h2","h3","h4","h5","p","li","td","th","dt","dd"]):
        text = el.get_text(separator=" ", strip=True)
        if not text or len(text) < 3:
            continue

        if el.name in heading_tags:
            flush_section()
            current_title = text
            raw_key  = re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_') or "section"
            key      = raw_key
            counter  = 2
            while key in sections:
                key = f"{raw_key}_{counter}"
                counter += 1
            current_key = key
            current_buf = []
        else:
            current_buf.append(text)

    flush_section()

    print(f" Extracted {len(sections)} sections")
    for k, v in sections.items():
        print(f"   [{v['char_count']:>5} chars]  {v['title']}")

    return sections



#  STAGE 2 — LLM TRIPLE EXTRACTION  


def _build_system_prompt() -> str:
    """
    Builds the full system prompt at runtime.
    No class names or predicate examples are hardcoded here —
    the schema's own field descriptions guide the LLM completely.
    """
    schema_str = json.dumps(OntologyData.model_json_schema(), indent=2)
    return f"""You are an expert Semantic Web knowledge engineer.

Your task: read a section of text scraped from {TARGET_URL} and extract the richest possible set of semantic triples for an OWL ontology.

TRIPLE STRUCTURE:
  subject  ->  predicate  ->  object

STRICT RULES:
1. subjects and objects must be concise named entities — real people, programmes,
   labs, courses, research areas, awards, events, publications, departments, etc.
   Never use a full sentence as a subject or object.

2. predicates must be camelCase verb phrases that precisely describe the relationship.
   INVENT the best predicate for each fact. Do not limit yourself to any list.

3. subject_type and object_type: invent a PascalCase OWL class name that is as
   SPECIFIC as possible to the entity. Never use a generic fallback.
   Use "Literal" ONLY for plain data values: numbers, years, percentages, short
   descriptive strings that are not named entities.

4. confidence: be strict. Only 0.85+ for clearly stated, unambiguous facts.
   Use 0.6-0.84 for reasonable inferences. Never go below 0.5.

5. Extract up to {MAX_TRIPLES_PER_SEC} triples. Every triple must add NEW information.
   No duplicate or near-duplicate triples.

6. Output ONLY valid JSON conforming exactly to this schema — no markdown, no preamble:

{schema_str}
"""

def call_groq_with_retry(section_title: str, text: str, client: Groq) -> List[dict]:
    """
    Calls Groq for one section with retry + auto-pause on rate limits.
    Returns list of triple dicts, or [] on permanent failure.
    """
    system_prompt = _build_system_prompt()
    user_msg = (
        f"Section heading: \"{section_title}\"\n\n"
        f"Section text:\n{text}"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        if _shutdown_requested:
            return []
        try:
            print(f"   Groq call (attempt {attempt}/{MAX_RETRIES})…", end=" ", flush=True)
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg}
                ],
                response_format={"type": "json_object"},
                temperature=0.05,
                max_tokens=2048
            )

            raw_json  = response.choices[0].message.content
            parsed    = json.loads(raw_json)
            validated = OntologyData(**parsed)

            result = []
            for t in validated.triples:
                d = t.model_dump()
                if not d.get("source_section"):
                    d["source_section"] = section_title
                result.append(d)

            print(f" {len(result)} triples")
            return result

        except Exception as e:
            err_str = str(e).lower()
            print(f"  {e}")

            if any(kw in err_str for kw in ["429", "rate_limit", "rate limit", "quota", "token"]):
                print(f"\nRATE / TOKEN LIMIT — pausing {RATE_LIMIT_PAUSE}s")
                print("   Progress is saved. Ctrl+C now to exit and resume later.")
                for remaining in range(RATE_LIMIT_PAUSE, 0, -10):
                    if _shutdown_requested:
                        return []
                    print(f"    {remaining}s…", end="\r", flush=True)
                    time.sleep(10)
                print()
            else:
                time.sleep(4 * attempt)

    print(f"   Gave up on \"{section_title}\" after {MAX_RETRIES} attempts.")
    return []


def run_llm_extraction(sections: dict, checkpoint: dict) -> dict:
    """
    Processes each section through the LLM, skipping already-done ones.
    Saves checkpoint after every section.
    """
    client      = Groq(api_key=GROQ_API_KEY)
    processed   = set(checkpoint.get("processed_sections", []))
    all_triples = list(checkpoint.get("triples", []))

    remaining = [(k, v) for k, v in sections.items() if k not in processed]
    total     = len(sections)
    done      = len(processed)

    print(f"\n LLM Extraction — {done}/{total} done, {len(remaining)} remaining\n")

    for i, (sec_key, sec_val) in enumerate(remaining, start=1):
        if _shutdown_requested:
            print(" Shutdown — saving and stopping.")
            break

        print(f"[{done+i}/{total}]  \"{sec_val['title']}\"  ({sec_val['char_count']} chars)")

        new_triples = call_groq_with_retry(
            section_title = sec_val["title"],
            text          = sec_val["clean_text"],
            client        = client
        )

        all_triples.extend(new_triples)
        processed.add(sec_key)
        checkpoint["processed_sections"] = list(processed)
        checkpoint["triples"]            = all_triples
        save_checkpoint(checkpoint)
        save_triples_json(all_triples)

        print(f"    Saved  ({len(all_triples)} triples total so far)")

        if i < len(remaining):
            time.sleep(SECTION_DELAY)

    checkpoint["triples"] = all_triples
    return checkpoint


#  STAGE 3 — BUILD FULLY DYNAMIC OWL FROM TRIPLES


def _to_safe_uri(ns: Namespace, text: str) -> URIRef:
    """Converts any free text to a safe URI fragment."""
    clean   = re.sub(r'[^a-zA-Z0-9_\-]', '_', text.strip())
    clean   = re.sub(r'_+', '_', clean).strip('_')
    encoded = urllib.parse.quote(clean, safe='_-')
    return ns[encoded] if encoded else ns["Unknown"]

def _to_safe_predicate(ns: Namespace, pred: str) -> URIRef:
    """Strips non-alphanumeric chars from a predicate, falls back to relatedTo."""
    clean = re.sub(r'[^a-zA-Z0-9]', '', pred.strip())
    return ns[clean] if clean else ns["relatedTo"]

def _to_pascal_case(text: str) -> str:
    """Converts any string to PascalCase for use as a class name."""
    words = re.sub(r'[^a-zA-Z0-9]+', ' ', text).split()
    return ''.join(w.capitalize() for w in words) if words else "Entity"


def build_owl(triples: list, output_file: str):
    """
    Builds a fully dynamic OWL ontology.

    Every class and every property is created on-the-fly from what the LLM
    returned — no hardcoded lists anywhere. Three passes:

    Pass 1 — Collect all unique type strings -> declare OWL Classes
    Pass 2 — Collect all unique predicates   -> declare OWL Properties with domain/range
    Pass 3 — Insert all individuals and assertions with annotations
    """
    print(f"\n Building OWL ontology from {len(triples)} triples…")

    g   = Graph()
    ONT = Namespace(ONT_NS)
    g.bind(ONT_PREFIX, ONT)
    g.bind("owl",  OWL)
    g.bind("rdf",  RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd",  XSD)

    #  Ontology-level metadata 
    ont_uri = URIRef(ONT_NS)
    g.add((ont_uri, RDF.type,     OWL.Ontology))
    g.add((ont_uri, RDFS.label,   Literal(f"Knowledge Graph — {TARGET_URL}")))
    g.add((ont_uri, RDFS.comment, Literal(
        f"Auto-generated from {TARGET_URL} via Groq LLM ({GROQ_MODEL}). "
        f"{len(triples)} raw triples collected."
    )))
    g.add((ont_uri, ONT["sourceURL"],   Literal(TARGET_URL)))
    g.add((ont_uri, ONT["tripleCount"], Literal(len(triples), datatype=XSD.integer)))

    # Annotation properties (standard across all runs) 
    conf_prop = ONT["hasConfidence"]
    g.add((conf_prop, RDF.type,    OWL.AnnotationProperty))
    g.add((conf_prop, RDFS.label,  Literal("hasConfidence")))
    g.add((conf_prop, RDFS.comment, Literal("LLM confidence score 0–1 for this assertion")))

    sec_prop = ONT["extractedFromSection"]
    g.add((sec_prop, RDF.type,    OWL.AnnotationProperty))
    g.add((sec_prop, RDFS.label,  Literal("extractedFromSection")))
    g.add((sec_prop, RDFS.comment, Literal("Page section heading this triple was extracted from")))

    low_conf_prop = ONT["lowConfidenceFlag"]
    g.add((low_conf_prop, RDF.type,    OWL.AnnotationProperty))
    g.add((low_conf_prop, RDFS.label,  Literal("lowConfidenceFlag")))
    g.add((low_conf_prop, RDFS.comment, Literal("True when LLM confidence < 0.5 — treat with caution")))

    # Pass 1: declare all OWL Classes from type strings 
    all_type_strings = set()
    for t in triples:
        for field in ("subject_type", "object_type"):
            val = str(t.get(field, "")).strip()
            if val and val.lower() != "literal":
                all_type_strings.add(val)

    class_uri_map = {}   # raw type string -> URIRef
    for type_str in all_type_strings:
        pascal = _to_pascal_case(type_str)
        c_uri  = ONT[pascal]
        if c_uri not in class_uri_map.values():
            g.add((c_uri, RDF.type,        OWL.Class))
            g.add((c_uri, RDFS.label,      Literal(pascal)))
            g.add((c_uri, RDFS.subClassOf, OWL.Thing))
            g.add((c_uri, RDFS.comment,    Literal(
                f"Dynamically discovered class from LLM extraction of {TARGET_URL}"
            )))
        class_uri_map[type_str] = c_uri

    print(f"    {len(class_uri_map)} unique entity classes discovered")

    # Pass 2: declare all OWL Properties 
    # First occurrence of a predicate determines its domain/range.
    declared_predicates = {}   # pred_text -> URIRef

    for t in triples:
        pred_text = str(t.get("predicate",    "")).strip()
        obj_type  = str(t.get("object_type",  "")).strip()
        subj_type = str(t.get("subject_type", "")).strip()

        if not pred_text or pred_text in declared_predicates:
            continue

        pred_uri    = _to_safe_predicate(ONT, pred_text)
        is_datatype = obj_type.lower() == "literal"
        prop_type   = OWL.DatatypeProperty if is_datatype else OWL.ObjectProperty

        g.add((pred_uri, RDF.type,    prop_type))
        g.add((pred_uri, RDFS.label,  Literal(pred_text)))
        g.add((pred_uri, RDFS.comment, Literal("Auto-generated property from LLM extraction")))

        if subj_type and subj_type.lower() != "literal" and subj_type in class_uri_map:
            g.add((pred_uri, RDFS.domain, class_uri_map[subj_type]))

        if is_datatype:
            g.add((pred_uri, RDFS.range, XSD.string))
        elif obj_type and obj_type in class_uri_map:
            g.add((pred_uri, RDFS.range, class_uri_map[obj_type]))

        declared_predicates[pred_text] = pred_uri

    print(f"    {len(declared_predicates)} unique predicates discovered")

    #  Pass 3: insert all individuals and assertions 
    skipped  = 0
    inserted = 0

    for t in triples:
        subj_text  = str(t.get("subject",       "")).strip()
        pred_text  = str(t.get("predicate",      "")).strip()
        obj_text   = str(t.get("object",         "")).strip()
        subj_type  = str(t.get("subject_type",   "")).strip()
        obj_type   = str(t.get("object_type",    "")).strip()
        confidence = float(t.get("confidence",   0.5))
        src_sec    = str(t.get("source_section", "")).strip()

        if not subj_text or not pred_text or not obj_text:
            skipped += 1
            continue

        subj_uri = _to_safe_uri(ONT, subj_text)
        pred_uri = declared_predicates.get(pred_text, _to_safe_predicate(ONT, pred_text))

        # Subject individual
        g.add((subj_uri, RDF.type,   OWL.NamedIndividual))
        g.add((subj_uri, RDFS.label, Literal(subj_text)))
        if subj_type and subj_type in class_uri_map:
            g.add((subj_uri, RDF.type, class_uri_map[subj_type]))

        # The assertion
        if obj_type.lower() == "literal":
            g.add((subj_uri, pred_uri, Literal(obj_text)))
        else:
            obj_uri = _to_safe_uri(ONT, obj_text)
            g.add((obj_uri, RDF.type,   OWL.NamedIndividual))
            g.add((obj_uri, RDFS.label, Literal(obj_text)))
            if obj_type and obj_type in class_uri_map:
                g.add((obj_uri, RDF.type, class_uri_map[obj_type]))
            g.add((subj_uri, pred_uri, obj_uri))

        # Per-triple annotations
        g.add((subj_uri, conf_prop, Literal(round(confidence, 3), datatype=XSD.decimal)))
        if src_sec:
            g.add((subj_uri, sec_prop, Literal(src_sec)))
        if confidence < 0.5:
            g.add((subj_uri, low_conf_prop, Literal(True, datatype=XSD.boolean)))

        inserted += 1

    g.serialize(destination=output_file, format="xml")

    print(f" OWL saved → {output_file}")
    print(f"   Classes    : {len(class_uri_map)}")
    print(f"   Properties : {len(declared_predicates)}")
    print(f"   Statements : {len(g)}")
    print(f"   Inserted   : {inserted}  |  Skipped (malformed): {skipped}")



#  MAIN

def main():
    print("=" * 60)
    print("  Dynamic Ontology Pipeline")
    print("=" * 60)
    print(f"  Target     : {TARGET_URL}")
    print(f"  Namespace  : {ONT_NS}")
    print(f"  Checkpoint : {CHECKPOINT_FILE}")
    print(f"  OWL output : {OWL_FILE}")
    print(f"\n  Press Ctrl+C at any time — all progress is saved.\n")

    if not GROQ_API_KEY:
        print(" GROQ_API_KEY not set. Add it to a .env file or export it.")
        sys.exit(1)

    #  Stage 1: Scrape 
    if os.path.exists(RAW_JSON_FILE):
        print(f" Raw JSON found — skipping scrape.")
        with open(RAW_JSON_FILE, "r", encoding="utf-8") as f:
            sections = json.load(f)
        print(f"   {len(sections)} sections loaded from {RAW_JSON_FILE}")
    else:
        sections = scrape_single_page(TARGET_URL)
        with open(RAW_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(sections, f, indent=2, ensure_ascii=False)
        print(f" Raw JSON -> {RAW_JSON_FILE}")

    # Stage 2: LLM Extraction 
    checkpoint    = load_checkpoint()
    all_processed = set(checkpoint.get("processed_sections", []))

    if all_processed >= set(sections.keys()):
        print("\n All sections already processed — skipping LLM stage.")
    else:
        checkpoint = run_llm_extraction(sections, checkpoint)

    final_triples = checkpoint.get("triples", [])
    print(f"\n Total triples collected: {len(final_triples)}")

    if not final_triples:
        print("  No triples found. Run again after token limits reset.")
        sys.exit(0)

    # Stage 3: OWL 
    build_owl(final_triples, OWL_FILE)

    # Printing the final output files
    print("\n" + "=" * 60)
    print("  Complete")
    print("=" * 60)
    print(f"   Sections JSON : {RAW_JSON_FILE}")
    print(f"   Triples JSON  : {TRIPLES_FILE}")
    print(f"   OWL Ontology  : {OWL_FILE}")
    print(f"   Checkpoint    : {CHECKPOINT_FILE}")
    print("\n  Open the .owl file in Protege to explore the knowledge graph.")
    print("  Re-run at any time to resume from the checkpoint.")
    print("=" * 60)


if __name__ == "__main__":
    main()

import requests
from bs4 import BeautifulSoup
import json
import time
import re
import os
import sys
import signal 
import urllib.parse
from groq import Groq
from rdflib import Graph, Literal, RDF, RDFS, OWL, URIRef, Namespace, XSD
from pydantic import BaseModel, Field
from typing import List, Optional


#  CONFIG  — edit these to tune behaviour

TARGET_URL        = "https://ece.iiitb.ac.in/"

from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL        = "llama-3.3-70b-versatile"

# Files
CHECKPOINT_FILE   = "ECE_V1_checkpoint.json"   # saves progress after every section
RAW_JSON_FILE     = "ECE_V1_raw.json" # all scraped sections (no LLM needed)
TRIPLES_FILE      = "ECE_V1_triples.json"       # accumulated LLM triples
OWL_FILE          = "ECE_V1_ontology.owl" # final output

# Token safety
SECTION_DELAY     = 3      # seconds to wait between Groq calls (avoid rate limits)
RATE_LIMIT_PAUSE  = 90     # seconds to pause when a 429 / quota error is detected
MAX_RETRIES       = 3      # retries per section before giving up on that section
MAX_CHARS_PER_SEC = 4000   # truncate section text before sending to LLM

# Quality control
MIN_SECTION_CHARS = 80     # sections shorter than this are skipped (too little info)
MAX_TRIPLES_PER_SEC = 25   # ask LLM for up to this many triples per section

# Ontology namespace
ONT_NS = "https://ece.iiitb.ac.in/ontology#"



#  PYDANTIC SCHEMA  — enriched triple with extra fields

class EnrichedTriple(BaseModel):
    subject:         str  = Field(description="Named entity — person, programme, lab, concept (concise noun phrase)")
    predicate:       str  = Field(description="camelCase relationship verb, e.g. teachesCourse, belongsToDepartment, hasResearchArea")
    object:          str  = Field(description="Target entity or literal value")
    subject_type:    str  = Field(description="OWL class for the subject: Faculty | Student | Course | Lab | Center | Department | ResearchArea | Programme | Publication | Event | Institute | Organization | GovernmentBody | Other")
    object_type:     str  = Field(description="OWL class for the object: Faculty | Student | Course | Lab | Center | Department | ResearchArea | Programme | Publication | Event | Institute | Organization | GovernmentBody | Literal | Other")
    confidence:      float = Field(description="Confidence score 0.0–1.0 for this triple")
    source_section:  str  = Field(description="Section heading from which this triple was extracted")

class OntologyData(BaseModel):
    triples: List[EnrichedTriple] = Field(description="List of enriched semantic triples")


#  GRACEFUL SHUTDOWN  — Ctrl+C saves and exits cleanly

_shutdown_requested = False

def _handle_sigint(sig, frame):
    global _shutdown_requested
    print("\n\n  Interrupt received. Finishing current section then saving…")
    _shutdown_requested = True

signal.signal(signal.SIGINT, _handle_sigint)



#  CHECKPOINT HELPERS

def load_checkpoint() -> dict:
    """Returns the checkpoint dict, or empty structure if none exists."""
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


#  STAGE 1 — SCRAPE & STRUCTURE THE SINGLE TARGET PAGE

def scrape_single_page(url: str) -> dict:
    """
    Deeply scrapes one page.
    Returns a dict of section_key -> {title, clean_text, char_count}.
    Also captures tables and definition lists for richer content.
    """
    print(f"\n Scraping: {url}")

    session = requests.Session()

    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry_strategy = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = session.get(
            url,
            headers=headers,
            timeout=(30, 120),
            allow_redirects=True,
            verify=False
        )
        resp.raise_for_status()

    except Exception as e:
        print(f" Failed to fetch page: {e}")

        print(" Trying fallback URL...")

        try:
            fallback_url = "https://ece.iiitb.ac.in/"
            resp = session.get(
                fallback_url,
                headers=headers,
                timeout=(30, 120),
                allow_redirects=True,
                verify=False
            )
            resp.raise_for_status()
            print(f" Fallback worked: {fallback_url}")

        except Exception as e2:
            print(f" Fallback also failed: {e2}")
            sys.exit(1)

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove boilerplate
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "noscript", "iframe", "form", "button"]):
        tag.decompose()

    sections = {}
    current_key = "overview"
    current_title = "Overview"
    current_buf = []

    def flush_section():
        if not current_buf:
            return

        raw = " ".join(current_buf)
        clean = re.sub(r'\s+', ' ', raw).strip()

        if len(clean) >= MIN_SECTION_CHARS:
            sections[current_key] = {
                "title": current_title,
                "clean_text": clean[:MAX_CHARS_PER_SEC],
                "char_count": len(clean)
            }

    heading_tags = {"h1", "h2", "h3", "h4", "h5"}

    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "td", "th", "dt", "dd"]):
        text = el.get_text(separator=" ", strip=True)

        if not text or len(text) < 3:
            continue

        if el.name in heading_tags:
            flush_section()
            current_title = text

            raw_key = re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')
            base_key = raw_key or "section"

            key = base_key
            counter = 2
            while key in sections:
                key = f"{base_key}_{counter}"
                counter += 1

            current_key = key
            current_buf = []

        else:
            current_buf.append(text)

    flush_section()

    print(f" Extracted {len(sections)} sections from the page.")
    for k, v in sections.items():
        print(f"   [{v['char_count']:>5} chars]  {v['title']}")

    return sections

#  STAGE 2 — LLM TRIPLE EXTRACTION (section by section)


SYSTEM_PROMPT = f"""You are an expert Semantic Web knowledge engineer specialising in university ontologies.

Your task: read a section of text from a faculty member's profile page at IIIT Bangalore and extract ENRICHED semantic triples.

CRITICAL INSTRUCTIONS FOR ACCURACY:
1. IGNORE WEBSITE NAVIGATION: Do not extract triples about generic university menus, "Departments", or lists of "Programmes" (like "B.Tech", "M.Tech") unless they are explicitly mentioned in a sentence as something the faculty member teaches or runs.
2. PRESERVE EXACT SEMANTICS: Do not abbreviate or loosely summarize relationships. If the text says "He heads Center Y, which is funded by Z", you MUST extract (Person -> headsCenter -> Y) and (Y -> fundedBy -> Z). Do NOT invent a shortcut like (Person -> collaboratesWith -> Z).
3. Each triple must be: subject → predicate → object
4. Predicates MUST be exact camelCase verbs that accurately reflect the text (e.g., headsCenter, fundedBy, servesOnAdvisoryPanel, hasSpecialisation). Avoid vague predicates if the text provides specific roles.
5. subjects and objects must be concise named entities (not sentences)
6. subject_type and object_type must be one of: Faculty | Student | Course | Lab | Center | Department | ResearchArea | Programme | Publication | Event | Institute | Organization | GovernmentBody | Literal | Other
7. confidence must reflect how certain you are this relationship is correct (0.0–1.0)
8. Extract up to {MAX_TRIPLES_PER_SEC} triples — precision and accuracy are your top priority.
9. Output ONLY valid JSON, no preamble, no markdown fences.
"""

def call_groq_with_retry(section_key: str, section_title: str, text: str, client: Groq) -> List[dict]:
    """
    Calls Groq API for one section. Handles rate limits with auto-pause.
    Returns list of triple dicts, or [] on permanent failure.
    """
    schema = OntologyData.model_json_schema()

    user_msg = (
        f"Section: \"{section_title}\"\n\n"
        f"Text:\n{text}\n\n"
        f"Output JSON must conform exactly to this schema:\n"
        f"{json.dumps(schema, indent=2)}"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        if _shutdown_requested:
            return []

        try:
            print(f"    Calling Groq (attempt {attempt}/{MAX_RETRIES})…", end=" ", flush=True)
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg}
                ],
                response_format={"type": "json_object"},
                temperature=0.05,   # very low — we want deterministic, factual output
                max_tokens=2048
            )

            raw_json = response.choices[0].message.content
            parsed   = json.loads(raw_json)
            validated = OntologyData(**parsed)

            # Attach source_section to any triple that didn't get it
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
            print(f"  Error: {e}")

            # Detect rate-limit / quota errors
            if "429" in err_str or "rate" in err_str or "quota" in err_str or "tokens" in err_str:
                print(f"\n TOKEN / RATE LIMIT HIT — pausing for {RATE_LIMIT_PAUSE}s")
                print("   All progress has been saved. You can Ctrl+C now and resume later.")
                for remaining in range(RATE_LIMIT_PAUSE, 0, -10):
                    if _shutdown_requested:
                        return []
                    print(f"    Resuming in {remaining}s…", end="\r", flush=True)
                    time.sleep(10)
                print()  # newline after countdown
                # retry after pause
            else:
                # Non-rate-limit error: wait briefly then retry
                time.sleep(4 * attempt)

    print(f"    Gave up on section '{section_title}' after {MAX_RETRIES} attempts.")
    return []


def run_llm_extraction(sections: dict, checkpoint: dict) -> dict:
    """
    Iterates through sections, skips already-processed ones,
    calls LLM for each remaining section, updates checkpoint continuously.
    """
    client = Groq(api_key=GROQ_API_KEY)
    processed = set(checkpoint.get("processed_sections", []))
    all_triples = checkpoint.get("triples", [])

    remaining = [(k, v) for k, v in sections.items() if k not in processed]
    total = len(sections)
    done  = len(processed)

    print(f"\n LLM Extraction — {done}/{total} sections already done, {len(remaining)} remaining\n")

    for i, (sec_key, sec_val) in enumerate(remaining, start=1):
        if _shutdown_requested:
            print(" Shutdown requested — saving and exiting.")
            break

        print(f"[{done+i}/{total}] Section: \"{sec_val['title']}\" ({sec_val['char_count']} chars)")

        new_triples = call_groq_with_retry(
            section_key   = sec_key,
            section_title = sec_val["title"],
            text          = sec_val["clean_text"],
            client        = client
        )

        # Save immediately after each section
        all_triples.extend(new_triples)
        processed.add(sec_key)
        checkpoint["processed_sections"] = list(processed)
        checkpoint["triples"]            = all_triples
        save_checkpoint(checkpoint)
        save_triples_json(all_triples)

        print(f"    Checkpoint saved ({len(all_triples)} total triples so far)")

        if i < len(remaining):  # no need to sleep after the last one
            time.sleep(SECTION_DELAY)

    checkpoint["triples"] = all_triples
    return checkpoint


#  STAGE 3 — BUILD ENRICHED OWL FROM TRIPLES


# Map string type names → OWL class URIs (created inside the graph)
CLASS_LABELS = [
    "Faculty", "Student", "Course", "Lab", "Center", "Department",
    "ResearchArea", "Programme", "Publication", "Event", "Institute", 
    "Organization", "GovernmentBody", "Other"
]

def safe_uri(ns: Namespace, text: str) -> URIRef:
    """Creates a safe URI from free text."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', text.strip())
    clean = re.sub(r'_+', '_', clean).strip('_')
    clean = urllib.parse.quote(clean, safe='_-')
    return ns[clean] if clean else ns["Unknown"]

def safe_predicate(ns: Namespace, pred: str) -> URIRef:
    """Ensures predicate is valid camelCase URI."""
    clean = re.sub(r'[^a-zA-Z0-9]', '', pred)
    if not clean:
        clean = "relatedTo"
    return ns[clean]

def build_owl(triples: list, output_file: str):
    """
    Builds a richly annotated OWL ontology from the list of triple dicts.
    Each triple becomes:
      - subject  → rdf:type     → owl:NamedIndividual
      - subject  → rdf:type     → <SubjectClass>
      - subject  → <predicate>  → object
      - object   → rdf:type     → owl:NamedIndividual  (if not Literal)
      - object   → rdf:type     → <ObjectClass>
      - predicate → rdf:type    → owl:ObjectProperty or owl:DatatypeProperty
      - predicate → rdfs:label  → human-readable label
      - triple   → confidence annotation
    """
    print(f"\n  Building OWL ontology from {len(triples)} triples…")

    g   = Graph()
    ONT = Namespace(ONT_NS)
    g.bind("iiitb",  ONT)
    g.bind("owl",  OWL)
    g.bind("rdf",  RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd",  XSD)

    # ── Ontology header ─────────────────────────────────────
    ont_uri = URIRef(ONT_NS)
    g.add((ont_uri, RDF.type,            OWL.Ontology))
    g.add((ont_uri, RDFS.label,          Literal("ECE IIITB Knowledge Graph")))
    g.add((ont_uri, RDFS.comment,        Literal("Auto-generated from http://ece.iiitb.ac.in/ using Groq LLM triple extraction")))
    g.add((ont_uri, URIRef(ONT_NS + "generatedBy"),  Literal("ece_iiitb_pipeline.py")))
    g.add((ont_uri, URIRef(ONT_NS + "tripleCount"),  Literal(len(triples), datatype=XSD.integer)))

    # ── Define OWL Classes ──────────────────────────────────
    class_uris = {}
    for label in CLASS_LABELS:
        c_uri = ONT[label]
        g.add((c_uri, RDF.type,   OWL.Class))
        g.add((c_uri, RDFS.label, Literal(label)))
        g.add((c_uri, RDFS.subClassOf, OWL.Thing))
        class_uris[label] = c_uri

    # ── Confidence annotation property ──────────────────────
    conf_prop = ONT["hasConfidence"]
    g.add((conf_prop, RDF.type,   OWL.AnnotationProperty))
    g.add((conf_prop, RDFS.label, Literal("hasConfidence")))
    g.add((conf_prop, RDFS.comment, Literal("Confidence score (0–1) assigned by the LLM")))

    source_prop = ONT["extractedFromSection"]
    g.add((source_prop, RDF.type,   OWL.AnnotationProperty))
    g.add((source_prop, RDFS.label, Literal("extractedFromSection")))

    # ── Track declared predicates to avoid duplicate declarations ──
    declared_predicates = set()

    # ── Process each triple ─────────────────────────────────
    skipped = 0
    for t in triples:
        subj_text  = str(t.get("subject",      "")).strip()
        pred_text  = str(t.get("predicate",     "")).strip()
        obj_text   = str(t.get("object",        "")).strip()
        subj_type  = str(t.get("subject_type",  "Other")).strip()
        obj_type   = str(t.get("object_type",   "Other")).strip()
        confidence = float(t.get("confidence",  0.5))
        src_sec    = str(t.get("source_section","")).strip()

        # Skip low-quality or malformed triples
        if not subj_text or not pred_text or not obj_text:
            skipped += 1
            continue
        if confidence < 0.4:
            skipped += 1
            continue

        subj_uri = safe_uri(ONT, subj_text)
        pred_uri = safe_predicate(ONT, pred_text)

        # ── Subject individual ───────────────────────────────
        g.add((subj_uri, RDF.type,   OWL.NamedIndividual))
        g.add((subj_uri, RDFS.label, Literal(subj_text)))
        if subj_type in class_uris:
            g.add((subj_uri, RDF.type, class_uris[subj_type]))

        # ── Predicate declaration ────────────────────────────
        if pred_uri not in declared_predicates:
            is_literal_obj = (obj_type == "Literal")
            prop_type = OWL.DatatypeProperty if is_literal_obj else OWL.ObjectProperty
            g.add((pred_uri, RDF.type,   prop_type))
            g.add((pred_uri, RDFS.label, Literal(pred_text)))
            # Add rdfs:domain and rdfs:range hints
            if subj_type in class_uris:
                g.add((pred_uri, RDFS.domain, class_uris[subj_type]))
            if obj_type in class_uris and obj_type != "Literal":
                g.add((pred_uri, RDFS.range, class_uris[obj_type]))
            declared_predicates.add(pred_uri)

        # ── Object: NamedIndividual or Literal ──────────────
        if obj_type == "Literal":
            g.add((subj_uri, pred_uri, Literal(obj_text)))
        else:
            obj_uri = safe_uri(ONT, obj_text)
            g.add((obj_uri, RDF.type,   OWL.NamedIndividual))
            g.add((obj_uri, RDFS.label, Literal(obj_text)))
            if obj_type in class_uris:
                g.add((obj_uri, RDF.type, class_uris[obj_type]))
            g.add((subj_uri, pred_uri, obj_uri))

        # ── Annotations on the triple's subject ─────────────
        g.add((subj_uri, conf_prop,   Literal(round(confidence, 3), datatype=XSD.decimal)))
        if src_sec:
            g.add((subj_uri, source_prop, Literal(src_sec)))

    # ── Serialize ────────────────────────────────────────────
    g.serialize(destination=output_file, format="xml")

    total_stmts = len(g)
    print(f" OWL saved → {output_file}")
    print(f"   Classes: {len(CLASS_LABELS)} | Predicates: {len(declared_predicates)} | "
          f"Statements: {total_stmts} | Skipped triples: {skipped}")


#  MAIN ENTRY POINT

def main():
    print("=" * 60)
    print("    Quality Ontology Pipeline  ")
    print("=" * 60)
    print(f"Target  : {TARGET_URL}")
    print(f"Checkpoint: {CHECKPOINT_FILE}")
    print(f"Press Ctrl+C at any time to pause safely.\n")

    # ── Stage 1: Scrape ─────────────────────────────────────
    if os.path.exists(RAW_JSON_FILE):
        print(f" Raw JSON found ({RAW_JSON_FILE}) — skipping scrape.")
        with open(RAW_JSON_FILE, "r", encoding="utf-8") as f:
            sections = json.load(f)
        print(f"   Loaded {len(sections)} sections.")
    else:
        sections = scrape_single_page(TARGET_URL)
        with open(RAW_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(sections, f, indent=2, ensure_ascii=False)
        print(f" Raw JSON saved → {RAW_JSON_FILE}")

    # ── Stage 2: LLM Extraction ─────────────────────────────
    checkpoint = load_checkpoint()

    all_processed = set(checkpoint.get("processed_sections", []))
    if all_processed == set(sections.keys()):
        print("\n All sections already processed — skipping LLM stage.")
    else:
        checkpoint = run_llm_extraction(sections, checkpoint)

    final_triples = checkpoint.get("triples", [])
    print(f"\n Total triples collected: {len(final_triples)}")

    if not final_triples:
        print("  No triples found. Cannot generate OWL. Run again after token limits reset.")
        sys.exit(0)

    # ── Stage 3: OWL Generation ─────────────────────────────
    # Always regenerate OWL from whatever triples we have
    build_owl(final_triples, OWL_FILE)

    # ── Summary ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Pipeline Complete  ")
    print("=" * 60)
    print(f"   Raw sections  → {RAW_JSON_FILE}")
    print(f"   Triples JSON  → {TRIPLES_FILE}")
    print(f"   OWL Ontology  → {OWL_FILE}")
    print(f"   Checkpoint    → {CHECKPOINT_FILE}")
    print("\n  Open the .owl file in Protégé to browse the knowledge graph.")
    print("  To resume after a token pause: just run the script again.")
    print("=" * 60)


if __name__ == "__main__":
    main()

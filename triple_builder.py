"""
triple_builder.py — Convert enriched entities + relationships
into an rdflib Graph with proper OWL class hierarchy,
object properties (with domain/range), and datatype properties.
Produces a Protege-ready OWL ontology.
"""

import re
from rdflib import (Graph, Namespace, URIRef, Literal,
                    RDF, RDFS, OWL, XSD)
from rdflib.namespace import DC, FOAF, SKOS

# ── Namespaces ────────────────────────────────────────────
BASE_URI = "http://iiitb.ac.in/ontology/faculty#"
ONTO = Namespace(BASE_URI)
SCHEMA = Namespace("https://schema.org/")

# ── OWL Class definitions ─────────────────────────────────
CLASS_MAP = {
    "Thing":         OWL.Thing,
    "Person":        ONTO.Person,
    "Faculty":       ONTO.Faculty,
    "ResearchArea":  ONTO.ResearchArea,
    "Publication":   ONTO.Publication,
    "Project":       ONTO.Project,
    "Organization":  ONTO.Organization,
    "Award":         ONTO.Award,
    "Degree":        ONTO.Degree,
    "Student":       ONTO.Student,
    "Course":        ONTO.Course,
}

# ── Class hierarchy ───────────────────────────────────────
CLASS_HIERARCHY = {
    "Person":       "Thing",
    "Faculty":      "Person",
    "Student":      "Person",
    "Publication":  "Thing",
    "Project":      "Thing",
    "Organization": "Thing",
    "ResearchArea": "Thing",
    "Award":        "Thing",
    "Degree":       "Thing",
    "Course":       "Thing",
}

# ── Property schema (name: (domain, range, is_object_prop, comment)) ──
PROPERTY_SCHEMA = {
    # Object Properties
    "hasResearchArea":   ("Faculty",      "ResearchArea",  True,
                          "Links a faculty member to their research areas"),
    "authorOf":          ("Faculty",      "Publication",   True,
                          "Links a faculty to a publication they authored"),
    "worksAt":           ("Faculty",      "Organization",  True,
                          "Links a faculty to their institution"),
    "belongsTo":         ("Faculty",      "Organization",  True,
                          "Links a faculty to their department/group"),
    "supervisesStudent": ("Faculty",      "Student",       True,
                          "Links a faculty to a PhD/research student they supervise"),
    "receivedAward":     ("Person",       "Award",         True,
                          "Links a person to an award they received"),
    "teaches":           ("Faculty",      "Course",        True,
                          "Links a faculty to a course they teach"),
    "worksOnProject":    ("Faculty",      "Project",       True,
                          "Links a faculty to a project they work on"),
    "hasEducation":      ("Person",       "Degree",        True,
                          "Links a person to an academic degree they hold"),
    "publishedIn":       ("Publication",  "Organization",  True,
                          "Links a publication to the venue/journal it was published in"),
    "fundedBy":          ("Project",      "Organization",  True,
                          "Links a project to its funding organization"),
    "collaboratesWith":  ("Faculty",      "Faculty",       True,
                          "Links two collaborating faculty members"),
    "isAffiliatedWith":  ("Person",       "Organization",  True,
                          "Links a person to an affiliated organization"),
    "memberOf":          ("Person",       "Organization",  True,
                          "Links a person to an organization they are member of"),
    "relatedTo":         ("ResearchArea", "ResearchArea",  True,
                          "Links related research areas"),
    "cites":             ("Publication",  "Publication",   True,
                          "Links a publication to one it cites"),
    # Inverse object properties
    "isResearchAreaOf":  ("ResearchArea", "Faculty",       True,
                          "Inverse of hasResearchArea"),
    "authoredBy":        ("Publication",  "Faculty",       True,
                          "Inverse of authorOf"),
    "employs":           ("Organization", "Faculty",       True,
                          "Inverse of worksAt"),
    "supervisedBy":      ("Student",      "Faculty",       True,
                          "Inverse of supervisesStudent"),
    "awardedTo":         ("Award",        "Person",        True,
                          "Inverse of receivedAward"),
    "taughtBy":          ("Course",       "Faculty",       True,
                          "Inverse of teaches"),
    "hasParticipant":    ("Project",      "Faculty",       True,
                          "Inverse of worksOnProject"),

    # Datatype Properties
    "fullName":           ("Person",       "xsd:string",   False,
                           "Full name of the person"),
    "emailAddress":       ("Person",       "xsd:string",   False,
                           "Email address"),
    "phoneNumber":        ("Person",       "xsd:string",   False,
                           "Phone number"),
    "jobTitle":           ("Faculty",      "xsd:string",   False,
                           "Job title/designation"),
    "publicationTitle":   ("Publication",  "xsd:string",   False,
                           "Title of the publication"),
    "publicationYear":    ("Publication",  "xsd:gYear",    False,
                           "Year of publication"),
    "publicationVenue":   ("Publication",  "xsd:string",   False,
                           "Journal or conference name"),
    "projectTitle":       ("Project",      "xsd:string",   False,
                           "Title of the project"),
    "projectFunding":     ("Project",      "xsd:string",   False,
                           "Funding amount or grant details"),
    "degreeLevel":        ("Degree",       "xsd:string",   False,
                           "Level of degree (PhD, MTech, BTech, etc.)"),
    "institution":        ("Degree",       "xsd:string",   False,
                           "Institution where degree was obtained"),
    "degreeYear":         ("Degree",       "xsd:gYear",    False,
                           "Year degree was awarded"),
    "awardTitle":         ("Award",        "xsd:string",   False,
                           "Name/title of the award"),
    "awardYear":          ("Award",        "xsd:gYear",    False,
                           "Year award was received"),
    "awardOrganization":  ("Award",        "xsd:string",   False,
                           "Organization that gave the award"),
    "researchKeyword":    ("ResearchArea", "xsd:string",   False,
                           "Keyword describing the research area"),
    "courseCode":         ("Course",       "xsd:string",   False,
                           "Course code"),
    "courseTitle":        ("Course",       "xsd:string",   False,
                           "Full title of the course"),
    "studentName":        ("Student",      "xsd:string",   False,
                           "Name of the student"),
    "studentType":        ("Student",      "xsd:string",   False,
                           "Type: PhD, MTech, BTech, etc."),
    "description":        (None,           "xsd:string",   False,
                           "General description"),
}

# Inverse property pairs
INVERSE_PAIRS = {
    "hasResearchArea":   "isResearchAreaOf",
    "authorOf":          "authoredBy",
    "worksAt":           "employs",
    "supervisesStudent": "supervisedBy",
    "receivedAward":     "awardedTo",
    "teaches":           "taughtBy",
    "worksOnProject":    "hasParticipant",
}


def _safe_uri(id_str: str) -> URIRef:
    """Convert any string to a safe URI fragment."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_",
                  str(id_str).strip())
    safe = re.sub(r"_+", "_", safe).strip("_")
    return ONTO[safe or "unknown"]


def _xsd_range(type_str: str) -> URIRef:
    """Resolve xsd:type string to rdflib XSD URI."""
    t = type_str.replace("xsd:", "").strip()
    return XSD[t] if t else XSD.string


def build_graph(enriched_list: list) -> Graph:
    """
    Build a fully annotated OWL graph from enriched chunks.
    """
    g = Graph()

    # Bind namespaces
    g.bind("onto",   ONTO)
    g.bind("owl",    OWL)
    g.bind("rdfs",   RDFS)
    g.bind("xsd",    XSD)
    g.bind("foaf",   FOAF)
    g.bind("schema", SCHEMA)
    g.bind("dc",     DC)
    g.bind("skos",   SKOS)

    # ── Ontology header ───────────────────────────────────
    onto_uri = URIRef(BASE_URI)
    g.add((onto_uri, RDF.type, OWL.Ontology))
    g.add((onto_uri, DC.title,
           Literal("IIITB Faculty Knowledge Ontology",
                   lang="en")))
    g.add((onto_uri, DC.description,
           Literal("OWL ontology for IIITB faculty "
                   "profile — Debabrata Das. "
                   "Auto-generated via semantic pipeline.",
                   lang="en")))
    g.add((onto_uri, OWL.versionInfo,
           Literal("1.0")))

    # ── Declare all OWL classes ───────────────────────────
    for name, cls_uri in CLASS_MAP.items():
        if name == "Thing":
            continue
        g.add((cls_uri, RDF.type, OWL.Class))
        g.add((cls_uri, RDFS.label,
               Literal(name, lang="en")))
        parent_name = CLASS_HIERARCHY.get(name, "Thing")
        parent_uri = CLASS_MAP.get(parent_name, OWL.Thing)
        g.add((cls_uri, RDFS.subClassOf, parent_uri))

    # ── Declare all properties ────────────────────────────
    for prop_name, (dom, rng, is_obj, comment) in \
            PROPERTY_SCHEMA.items():
        p_uri = ONTO[prop_name]

        if is_obj:
            g.add((p_uri, RDF.type, OWL.ObjectProperty))
        else:
            g.add((p_uri, RDF.type,
                   OWL.DatatypeProperty))

        g.add((p_uri, RDFS.label,
               Literal(prop_name, lang="en")))
        g.add((p_uri, RDFS.comment,
               Literal(comment, lang="en")))

        # Domain
        if dom and dom in CLASS_MAP:
            g.add((p_uri, RDFS.domain, CLASS_MAP[dom]))

        # Range
        if rng:
            if is_obj and rng in CLASS_MAP:
                g.add((p_uri, RDFS.range,
                       CLASS_MAP[rng]))
            elif not is_obj:
                g.add((p_uri, RDFS.range,
                       _xsd_range(rng)))

    # ── Declare inverse properties ────────────────────────
    for prop, inv_prop in INVERSE_PAIRS.items():
        p_uri = ONTO[prop]
        inv_uri = ONTO[inv_prop]
        g.add((p_uri, OWL.inverseOf, inv_uri))
        g.add((inv_uri, OWL.inverseOf, p_uri))

    # ── Process enriched chunks ───────────────────────────
    entity_type_map = {}  # id → type (for relationship validation)
    total_entities = 0
    total_rels = 0
    skipped_rels = 0

    for chunk_idx, chunk_result in enumerate(enriched_list):
        if not isinstance(chunk_result, dict):
            continue

        entities  = chunk_result.get("entities", [])
        rels      = chunk_result.get("relationships", [])
        annots    = chunk_result.get("owl_annotations", {})

        # ── Add entities as OWL Named Individuals ─────────
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            eid_str  = ent.get("id", "")
            etype    = ent.get("type", "Thing")
            elabel   = ent.get("label", eid_str)
            eprops   = ent.get("properties", {})

            if not eid_str:
                continue

            eid_uri = _safe_uri(eid_str)
            entity_type_map[eid_str] = etype

            # Type assertion
            cls_uri = CLASS_MAP.get(etype, ONTO[etype])
            g.add((eid_uri, RDF.type, OWL.NamedIndividual))
            g.add((eid_uri, RDF.type, cls_uri))
            g.add((eid_uri, RDFS.label,
                   Literal(elabel, lang="en")))

            # Entity properties as datatype assertions
            for pk, pv in eprops.items():
                if pv is None or str(pv).strip() == "":
                    continue
                # Determine URI for this property
                if pk in PROPERTY_SCHEMA:
                    dp_uri = ONTO[pk]
                    _, rng, is_obj, _ = PROPERTY_SCHEMA[pk]
                    if not is_obj:
                        g.add((dp_uri, RDF.type,
                               OWL.DatatypeProperty))
                        g.add((eid_uri, dp_uri,
                               Literal(str(pv),
                                       datatype=_xsd_range(rng))))
                else:
                    # Dynamic property not in schema
                    dp_uri = ONTO["prop_" + re.sub(
                        r"[^a-zA-Z0-9]", "_", pk)]
                    g.add((dp_uri, RDF.type,
                           OWL.DatatypeProperty))
                    g.add((dp_uri, RDFS.label,
                           Literal(pk)))
                    g.add((eid_uri, dp_uri,
                           Literal(str(pv))))

            total_entities += 1

        # ── Add relationships as triples ──────────────────
        for rel in rels:
            if not isinstance(rel, dict):
                continue

            subj_id   = rel.get("subject_id", "")
            pred_name = rel.get("predicate", "")
            obj_id    = rel.get("object_id", "")
            obj_type  = rel.get("object_type", "literal")
            datatype  = rel.get("datatype", "xsd:string")
            confidence= float(rel.get("confidence", 1.0))

            if not (subj_id and pred_name and obj_id):
                skipped_rels += 1
                continue

            subj_uri = _safe_uri(subj_id)
            pred_uri = ONTO[pred_name]

            if obj_type == "entity":
                obj_uri = _safe_uri(str(obj_id))
                g.add((subj_uri, pred_uri, obj_uri))

                # Ensure predicate is typed
                if pred_name not in PROPERTY_SCHEMA:
                    g.add((pred_uri, RDF.type,
                           OWL.ObjectProperty))
                    g.add((pred_uri, RDFS.label,
                           Literal(pred_name)))
            else:
                dt_uri = _xsd_range(datatype)
                g.add((subj_uri, pred_uri,
                       Literal(str(obj_id),
                               datatype=dt_uri)))
                if pred_name not in PROPERTY_SCHEMA:
                    g.add((pred_uri, RDF.type,
                           OWL.DatatypeProperty))
                    g.add((pred_uri, RDFS.label,
                           Literal(pred_name)))

            # Low confidence annotation
            if confidence < 0.7:
                g.add((pred_uri, ONTO.inferenceConfidence,
                       Literal(round(confidence, 2),
                               datatype=XSD.float)))

            total_rels += 1

        # ── Apply LLM-suggested OWL annotations ──────────
        for pred_name, dom_class in \
                annots.get("domain_hints", {}).items():
            if dom_class in CLASS_MAP:
                g.add((ONTO[pred_name], RDFS.domain,
                       CLASS_MAP[dom_class]))

        for pred_name, rng_val in \
                annots.get("range_hints", {}).items():
            if rng_val in CLASS_MAP:
                g.add((ONTO[pred_name], RDFS.range,
                       CLASS_MAP[rng_val]))
            elif rng_val.startswith("xsd:"):
                g.add((ONTO[pred_name], RDFS.range,
                       _xsd_range(rng_val)))

        for pred_name, inv_name in \
                annots.get("inverse_of", {}).items():
            g.add((ONTO[pred_name], OWL.inverseOf,
                   ONTO[inv_name]))

        for prop_name in \
                annots.get("functional_properties", []):
            g.add((ONTO[prop_name], RDF.type,
                   OWL.FunctionalProperty))

        for prop_name in \
                annots.get("symmetric_properties", []):
            g.add((ONTO[prop_name], RDF.type,
                   OWL.SymmetricProperty))

    print(f"\n  [triples] ✓ Graph built:")
    print(f"    Total triples : {len(g)}")
    print(f"    Entities      : {total_entities}")
    print(f"    Relationships : {total_rels}")
    print(f"    Skipped rels  : {skipped_rels}")
    print(f"    Classes       : {len(CLASS_MAP) - 1}")
    print(f"    Properties    : {len(PROPERTY_SCHEMA)}")
    return g

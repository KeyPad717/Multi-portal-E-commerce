import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, BNode
    from rdflib.namespace import XSD, FOAF, SKOS, DC
except ImportError:
    print("rdflib not found. Install it with:  pip install rdflib")
    sys.exit(1)

# NAMESPACES
BASE    = "http://semanticweb.iiitb.ac.in/"
EDU     = Namespace(BASE + "edu#")       # ontology schema
IIITB   = Namespace(BASE + "iiitb/")    # institution-specific individuals
SCHEMA  = Namespace("https://schema.org/")

OUTPUT_DIR = Path(__file__).parent / "output"

# HELPERS
def safe_slug(text: str) -> str:
    """Convert arbitrary text to a URI-safe slug."""
    text = text.strip()
    text = re.sub(r"[^\w\s-]", "", text)      # Remove special chars
    text = re.sub(r"[\s\-]+", "_", text)       # Spaces/dashes → underscore
    text = re.sub(r"_+", "_", text)            # Collapse multiple underscores
    return text.strip("_")[:120]               # Max 120 chars

def uri(namespace, *parts) -> URIRef:
    """Build a URIRef from namespace + parts, safely slugged."""
    slug = "_".join(safe_slug(str(p)) for p in parts if p)
    return namespace[slug]

def load_json(filename: str):
    """Load a JSON file from the output directory."""
    path = OUTPUT_DIR / filename
    if not path.exists():
        print(f"  ⚠  File not found: {filename}")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # master.json is a dict of lists, flatten all values
        result = []
        for v in data.values():
            if isinstance(v, list):
                result.extend(v)
        return result
    return data  # list files

def add_literal(g, subject, predicate, value, datatype=XSD.string):
    """Add a non-empty literal triple."""
    if value and str(value).strip():
        g.add((subject, predicate, Literal(str(value).strip(), datatype=datatype)))

def add_uri_prop(g, subject, predicate, url_str):
    """Add a URL as anyURI literal if non-empty."""
    if url_str and str(url_str).strip():
        g.add((subject, predicate, Literal(url_str.strip(), datatype=XSD.anyURI)))

# TBOX — Ontology Schema (classes & properties)

def build_tbox(g: Graph):
    """Define OWL classes, object properties and data properties."""

    print("Building TBox (schema)")

    # Ontology metadata
    onto = IIITB["ontology"]
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, RDFS.label, Literal("IIITB Institutional Knowledge Graph", lang="en")))
    g.add((onto, DC.creator, Literal("IIITB DM Project — json_to_owl.py")))
    g.add((onto, DC.date, Literal(datetime.now().isoformat(), datatype=XSD.dateTime)))

    # OWL Classes
    classes = { 
        "Institution"       : ("Educational institution (university, college, etc.)", SCHEMA.EducationalOrganization),
        "Department"        : ("Academic department within an institution", SCHEMA.Organization),
        "Faculty"           : ("Academic faculty member / professor", FOAF.Person),
        "Staff"             : ("Administrative / technical staff member", FOAF.Person),
        "ResearchScholar"   : ("PhD / MS research scholar", FOAF.Person),
        "GovernanceMember"  : ("Governing body / board member", FOAF.Person),
        "AcademicProgram"   : ("Academic programme offered by an institution", SCHEMA.EducationalOccupationalProgram),
        "UGProgram"         : ("Undergraduate programme (B.Tech, etc.)", None),
        "PGProgram"         : ("Postgraduate / masters programme (M.Tech, PGD, etc.)", None),
        "ResearchProgram"   : ("Research programme (PhD, MS by Research)", None),
        "Lab"               : ("Research lab or centre at the institution", SCHEMA.ResearchProject),
        "ResearchArea"      : ("Research domain / topic (SKOS concept)", SKOS.Concept),
        "NewsItem"          : ("News article or event published by the institution", SCHEMA.NewsArticle),
        "PlacementRecord"   : ("Placement / recruitment record", None),
        "StudentActivity"   : ("Student club, committee or campus event", None),
        "ExternalOrg"       : ("External organisation referenced by the institution", FOAF.Organization),
    }

    for cls_name, (comment, eq_class) in classes.items():
        cls_uri = EDU[cls_name]
        g.add((cls_uri, RDF.type, OWL.Class))
        g.add((cls_uri, RDFS.label, Literal(cls_name, lang="en")))
        g.add((cls_uri, RDFS.comment, Literal(comment, lang="en")))
        if eq_class:
            g.add((cls_uri, OWL.equivalentClass, eq_class))

    # Sub-class relationships
    g.add((EDU.UGProgram,       RDFS.subClassOf, EDU.AcademicProgram))
    g.add((EDU.PGProgram,       RDFS.subClassOf, EDU.AcademicProgram))
    g.add((EDU.ResearchProgram, RDFS.subClassOf, EDU.AcademicProgram))
    g.add((EDU.Faculty,         RDFS.subClassOf, FOAF.Person))
    g.add((EDU.Staff,           RDFS.subClassOf, FOAF.Person))
    g.add((EDU.ResearchScholar, RDFS.subClassOf, FOAF.Person))
    g.add((EDU.GovernanceMember,RDFS.subClassOf, FOAF.Person))
    g.add((EDU.Department,      RDFS.subClassOf, EDU.Institution))

    # Object Properties
    obj_props = [
        ("belongsTo",       "Faculty/Staff/Lab belongs to Institution",     None,               EDU.Institution),
        ("offers",          "Institution offers AcademicProgram",            EDU.Institution,    EDU.AcademicProgram),
        ("hasLab",          "Institution/Department has Lab",                None,               EDU.Lab),
        ("hasDepartment",   "Institution has Department",                    EDU.Institution,    EDU.Department),
        ("worksIn",         "Faculty/Scholar works in Lab",                  None,               EDU.Lab),
        ("hasResearchArea", "Faculty/Lab has ResearchArea",                  None,               EDU.ResearchArea),
        ("supervisedBy",    "ResearchScholar supervised by Faculty",         EDU.ResearchScholar,EDU.Faculty),
        ("governs",         "GovernanceMember governs Institution",          EDU.GovernanceMember,EDU.Institution),
        ("collaboratesWith","Institution collaborates with ExternalOrg",     EDU.Institution,    EDU.ExternalOrg),
        ("partOf",          "Department is part of Institution",             EDU.Department,     EDU.Institution),
        ("relatedTo",       "Generic semantic relation between any entities",None,               None),
    ]

    for prop_name, comment, domain, range_ in obj_props:
        prop = EDU[prop_name]
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.label, Literal(prop_name, lang="en")))
        g.add((prop, RDFS.comment, Literal(comment, lang="en")))
        if domain:
            g.add((prop, RDFS.domain, domain))
        if range_:
            g.add((prop, RDFS.range, range_))

    # Data Properties
    data_props = [
        ("name",            "Full name of the entity",                      XSD.string),
        ("email",           "Email address",                                 XSD.string),
        ("url",             "Web URL of the entity",                         XSD.anyURI),
        ("description",     "Textual description",                           XSD.string),
        ("designation",     "Job title / designation",                       XSD.string),
        ("bio",             "Biographical information",                      XSD.string),
        ("slug",            "URL slug identifier",                           XSD.string),
        ("category",        "Source category from scraper",                  XSD.string),
        ("body",            "Full body text scraped from the page",          XSD.string),
        ("scrapedAt",       "Timestamp when this data was scraped",          XSD.dateTime),
        ("publishedDate",   "Date of publication (news/events)",             XSD.string),
        ("fee",             "Programme fee per semester",                     XSD.string),
        ("admissionDeadline","Applications deadline",                        XSD.string),
        ("heading",         "Section heading extracted from the page",       XSD.string),
    ]

    for prop_name, comment, range_dt in data_props:
        prop = EDU[prop_name]
        g.add((prop, RDF.type, OWL.DatatypeProperty))
        g.add((prop, RDFS.label, Literal(prop_name, lang="en")))
        g.add((prop, RDFS.comment, Literal(comment, lang="en")))
        g.add((prop, RDFS.range, range_dt))

    print(f"     TBox triples so far: {len(g)}")


# ABOX — Individual Instances

def add_institution(g: Graph) -> URIRef:
    """Create the top-level IIITB institution individual."""
    print("Adding Institution")
    inst = IIITB["IIIT_Bangalore"]
    g.add((inst, RDF.type, EDU.Institution))
    g.add((inst, RDF.type, OWL.NamedIndividual))
    g.add((inst, EDU.name, Literal("International Institute of Information Technology Bangalore", datatype=XSD.string)))
    g.add((inst, EDU.url, Literal("https://www.iiitb.ac.in/", datatype=XSD.anyURI)))
    g.add((inst, RDFS.label, Literal("IIIT Bangalore", lang="en")))
    # Known departments  (will be enriched from faculty/labs data)
    dept_map = {
        "CSE" : ("Department of Computer Science & Engineering",     "https://cse.iiitb.ac.in/"),
        "DSAI": ("Department of Data Science and Artificial Intelligence", "https://dsai.iiitb.ac.in/"),
        "ECE" : ("Department of Electronics and Communication Engineering","https://ece.iiitb.ac.in/"),
        "DHSS": ("Department of Digital Humanities and Societal Systems",  "https://dhss.iiitb.ac.in/"),
    }
    for code, (name, dept_url) in dept_map.items():
        dept = IIITB[f"dept_{code}"]
        g.add((dept, RDF.type, EDU.Department))
        g.add((dept, RDF.type, OWL.NamedIndividual))
        g.add((dept, EDU.name, Literal(name, datatype=XSD.string)))
        g.add((dept, EDU.url, Literal(dept_url, datatype=XSD.anyURI)))
        g.add((dept, RDFS.label, Literal(name, lang="en")))
        g.add((inst, EDU.hasDepartment, dept))
        g.add((dept, EDU.partOf, inst))
    return inst


def process_faculty(g: Graph, inst: URIRef):
    """Process faculty.json → edu:Faculty and edu:ResearchArea individuals."""
    print("Processing Faculty")
    data = load_json("faculty.json")
    seen_names, seen_slugs = set(), set()
    count = 0

    for item in data:
        cat = item.get("category", "")

        # Faculty profile
        if cat == "faculty_profile":
            name = item.get("name", "").strip()
            slug = item.get("slug", "").strip()
            # Skip 404 / empty entries
            if not name or name in ("Page Not Found", "Quick Links", "Newsletter Sign Up"):
                continue
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            seen_names.add(name)

            fac = uri(IIITB, "faculty", slug or name)
            g.add((fac, RDF.type, EDU.Faculty))
            g.add((fac, RDF.type, OWL.NamedIndividual))
            g.add((fac, RDFS.label, Literal(name, lang="en")))
            add_literal(g, fac, EDU.name, name)
            add_literal(g, fac, EDU.slug, slug)
            add_uri_prop(g, fac, EDU.url, item.get("url"))
            add_literal(g, fac, EDU.designation, item.get("designation", ""))
            add_literal(g, fac, EDU.email, item.get("email", ""))
            add_literal(g, fac, EDU.bio, item.get("bio", ""))
            add_literal(g, fac, EDU.scrapedAt, item.get("_scraped_at", ""))
            g.add((fac, EDU.belongsTo, inst))

            # Research areas (list field)
            for area in item.get("areas", []):
                if area and area.strip():
                    area_uri = uri(IIITB, "area", area)
                    g.add((area_uri, RDF.type, EDU.ResearchArea))
                    g.add((area_uri, RDF.type, OWL.NamedIndividual))
                    add_literal(g, area_uri, EDU.name, area)
                    g.add((area_uri, RDFS.label, Literal(area, lang="en")))
                    g.add((fac, EDU.hasResearchArea, area_uri))
            count += 1

        # Faculty list page — extract departments from links
        elif cat == "faculty_list":
            for link in item.get("links", []):
                href = link.get("href", "")
                text = link.get("text", "").strip()
                if "Department of" in text and href.startswith("http"):
                    dept = uri(IIITB, "dept", text)
                    g.add((dept, RDF.type, EDU.Department))
                    g.add((dept, RDF.type, OWL.NamedIndividual))
                    add_literal(g, dept, EDU.name, text)
                    add_uri_prop(g, dept, EDU.url, href)
                    g.add((dept, RDFS.label, Literal(text, lang="en")))
                    g.add((inst, EDU.hasDepartment, dept))

    print(f"     Faculty profiles added: {count}")


def process_governance(g: Graph, inst: URIRef):
    """Process governance.json → edu:GovernanceMember, administration bios."""
    print("Processing Governance")
    data = load_json("governance.json")
    count = 0

    for item in data:
        cat  = item.get("category", "")
        url  = item.get("url", "")
        title = item.get("title", "").strip()
        body  = item.get("body", "").strip()

        if cat != "governance" or not title:
            continue

        # Distinguish person pages from policy/document pages
        is_person = any(kw in url for kw in ["/administration/", "/governing-body/"])

        ind = uri(IIITB, "governance", title)
        if is_person:
            g.add((ind, RDF.type, EDU.GovernanceMember))
        else:
            g.add((ind, RDF.type, EDU.Institution))      # policy pages linked to inst
            g.add((ind, RDFS.seeAlso, Literal(url, datatype=XSD.anyURI)))
            continue  # don't add a full individual for policy pages

        g.add((ind, RDF.type, OWL.NamedIndividual))
        g.add((ind, RDFS.label, Literal(title, lang="en")))
        add_literal(g, ind, EDU.name, title)
        add_uri_prop(g, ind, EDU.url, url)
        add_literal(g, ind, EDU.bio, body[:1000] if body else "")
        add_literal(g, ind, EDU.scrapedAt, item.get("_scraped_at", ""))
        g.add((ind, EDU.governs, inst))

        # Headings → roles/designations
        for heading in item.get("headings", []):
            skip_words = ["Quick Links", "Newsletter Sign Up", "Leadership Awards",
                          "Academic Awards"]
            if heading and heading not in skip_words:
                add_literal(g, ind, EDU.designation, heading)
                break  # take first valid heading as primary designation
        count += 1

    print(f"     Governance individuals added: {count}")


def process_programs(g: Graph, inst: URIRef):
    """Process programs.json → AcademicProgram individuals."""
    print("Processing Programs")
    data = load_json("programs.json")

    level_map = [
        ("B.Tech", EDU.UGProgram),
        ("Integrated M.Tech", EDU.PGProgram),
        ("M.Tech", EDU.PGProgram),
        ("M.Sc", EDU.PGProgram),
        ("Master of Science", EDU.ResearchProgram),
        ("Post Graduate Diploma", EDU.PGProgram),
        ("PG Diploma", EDU.PGProgram),
        ("Ph.D", EDU.ResearchProgram),
        ("Visvesvaraya", EDU.ResearchProgram),
        ("Fellowship", EDU.PGProgram),
    ]

    count = 0
    seen = set()

    for item in data:
        if item.get("category") != "program":
            continue
        title = item.get("title", "").strip()
        if not title or title in seen:
            continue
        seen.add(title)

        # Determine program level
        prog_class = EDU.AcademicProgram
        for keyword, cls in level_map:
            if keyword.lower() in title.lower():
                prog_class = cls
                break

        prog = uri(IIITB, "program", title)
        g.add((prog, RDF.type, prog_class))
        g.add((prog, RDF.type, OWL.NamedIndividual))
        g.add((prog, RDFS.label, Literal(title, lang="en")))
        add_literal(g, prog, EDU.name, title)
        add_uri_prop(g, prog, EDU.url, item.get("url"))
        add_literal(g, prog, EDU.description, item.get("description", ""))
        add_literal(g, prog, EDU.scrapedAt, item.get("_scraped_at", ""))
        g.add((inst, EDU.offers, prog))

        # structured_info — extract fees and deadlines as data properties
        si = item.get("structured_info", {})
        for k, v in si.items():
            if v and isinstance(v, str):
                k_lower = k.lower()
                if "fee" in k_lower or "per semester" in k_lower or "rs." in v.lower():
                    add_literal(g, prog, EDU.fee, f"{k}: {v}")
                elif "date" in k_lower or "deadline" in k_lower or "last date" in k_lower:
                    add_literal(g, prog, EDU.admissionDeadline, f"{k}: {v}")
                elif "research domain" not in k_lower:
                    # Add indicative research areas for research programs
                    if len(v) > 30:
                        add_literal(g, prog, EDU.description, f"{k}: {v[:500]}")

        count += 1

    print(f"     Programs added: {count}")


def process_labs(g: Graph, inst: URIRef):
    """Process labs_centers.json → edu:Lab individuals."""
    print("Processing Labs & Centers")
    data = load_json("labs_centers.json")

    seen_titles = set()
    count = 0

    for item in data:
        title = item.get("title", "").strip()
        url   = item.get("url", "").strip()

        if not title:
            continue
        # Deduplicate: same lab may appear across multiple pages
        if title in seen_titles:
            continue
        seen_titles.add(title)

        lab = uri(IIITB, "lab", title)
        g.add((lab, RDF.type, EDU.Lab))
        g.add((lab, RDF.type, OWL.NamedIndividual))
        g.add((lab, RDFS.label, Literal(title, lang="en")))
        add_literal(g, lab, EDU.name, title)
        add_uri_prop(g, lab, EDU.url, url)
        add_literal(g, lab, EDU.category, item.get("category", ""))
        add_literal(g, lab, EDU.scrapedAt, item.get("_scraped_at", ""))

        desc = item.get("description", "")
        if desc:
            add_literal(g, lab, EDU.description, desc[:800])

        g.add((inst, EDU.hasLab, lab))
        g.add((lab, EDU.belongsTo, inst))

        # People listed (usually empty but included for completeness)
        for person in item.get("people", []):
            if isinstance(person, str) and person.strip():
                p_uri = uri(IIITB, "person_lab", title, person)
                g.add((p_uri, RDF.type, EDU.Faculty))
                g.add((p_uri, RDF.type, OWL.NamedIndividual))
                add_literal(g, p_uri, EDU.name, person)
                g.add((p_uri, EDU.worksIn, lab))

        count += 1

    print(f"Labs/Centers added: {count}")


def process_research_scholars(g: Graph, inst: URIRef):
    """Process research_scholars.json → scholar list pages as ResearchProgram links."""
    print("Processing Research Scholars")
    data = load_json("research_scholars.json")
    count = 0

    for item in data:
        cat   = item.get("category", "")
        title = item.get("title", "").strip()
        url   = item.get("url", "").strip()

        if cat == "scholar_list" and title:
            # These are list pages for scholar categories
            prog = uri(IIITB, "scholar_program", title)
            g.add((prog, RDF.type, EDU.ResearchProgram))
            g.add((prog, RDF.type, OWL.NamedIndividual))
            g.add((prog, RDFS.label, Literal(title, lang="en")))
            add_literal(g, prog, EDU.name, title)
            add_uri_prop(g, prog, EDU.url, url)
            add_literal(g, prog, EDU.scrapedAt, item.get("_scraped_at", ""))
            g.add((inst, EDU.offers, prog))
            count += 1

        elif cat == "scholar_profile":
            name = item.get("name", "").strip()
            slug = item.get("slug", "").strip()
            if not name or name == "Page Not Found":
                continue
            scholar = uri(IIITB, "scholar", slug or name)
            g.add((scholar, RDF.type, EDU.ResearchScholar))
            g.add((scholar, RDF.type, OWL.NamedIndividual))
            g.add((scholar, RDFS.label, Literal(name, lang="en")))
            add_literal(g, scholar, EDU.name, name)
            add_literal(g, scholar, EDU.slug, slug)
            add_uri_prop(g, scholar, EDU.url, url)
            add_literal(g, scholar, EDU.scrapedAt, item.get("_scraped_at", ""))
            g.add((scholar, EDU.belongsTo, inst))
            count += 1

    print(f"     Scholar individuals added: {count}")


def process_staff(g: Graph, inst: URIRef):
    """Process staff.json → edu:Staff individuals."""
    print("Processing Staff")
    data = load_json("staff.json")
    seen = set()
    count = 0

    for item in data:
        cat  = item.get("category", "")
        if cat != "staff_profile":
            continue
        name = item.get("name", "").strip()
        slug = item.get("slug", "").strip()
        if not name or name in seen:
            continue
        seen.add(name)

        s = uri(IIITB, "staff", slug or name)
        g.add((s, RDF.type, EDU.Staff))
        g.add((s, RDF.type, OWL.NamedIndividual))
        g.add((s, RDFS.label, Literal(name, lang="en")))
        add_literal(g, s, EDU.name, name)
        add_literal(g, s, EDU.slug, slug)
        add_uri_prop(g, s, EDU.url, item.get("url"))
        add_literal(g, s, EDU.designation, item.get("designation", ""))
        add_literal(g, s, EDU.email, item.get("email", ""))
        add_literal(g, s, EDU.scrapedAt, item.get("_scraped_at", ""))
        g.add((s, EDU.belongsTo, inst))
        count += 1

    print(f"     Staff individuals added: {count}")


def process_placement(g: Graph, inst: URIRef):
    """Process placement.json → edu:PlacementRecord individuals."""
    print("Processing Placement")
    data = load_json("placement.json")
    count = 0

    for item in data:
        cat   = item.get("category", "")
        title = item.get("title", "").strip()
        url   = item.get("url", "").strip()
        body  = item.get("body", "").strip()

        if cat != "placement" or not title:
            continue

        p = uri(IIITB, "placement", title)
        g.add((p, RDF.type, EDU.PlacementRecord))
        g.add((p, RDF.type, OWL.NamedIndividual))
        g.add((p, RDFS.label, Literal(title, lang="en")))
        add_literal(g, p, EDU.name, title)
        add_uri_prop(g, p, EDU.url, url)
        add_literal(g, p, EDU.body, body[:800] if body else "")
        add_literal(g, p, EDU.scrapedAt, item.get("_scraped_at", ""))

        # Headings → section headers as metadata
        for h in item.get("headings", []):
            if h and h not in ("Quick Links", "Newsletter Sign Up"):
                add_literal(g, p, EDU.heading, h)

        g.add((p, EDU.belongsTo, inst))
        count += 1

    print(f"     Placement records added: {count}")


def process_news(g: Graph, inst: URIRef):
    """Process news.json → edu:NewsItem individuals."""
    print("Processing News & Events")
    data = load_json("news.json")
    seen_urls = set()
    count = 0

    for item in data:
        url   = item.get("url", "").strip()
        title = item.get("title", "").strip()
        body  = item.get("body", "").strip()
        date  = item.get("date", "").strip()
        cat   = item.get("category", "")

        # Skip empty / duplicate entries
        if not url or url in seen_urls:
            continue
        if not title and not body:
            continue
        seen_urls.add(url)

        display_title = title or f"News_{url[-30:]}"
        n = uri(IIITB, "news", url)
        g.add((n, RDF.type, EDU.NewsItem))
        g.add((n, RDF.type, OWL.NamedIndividual))
        label = title if title else display_title
        g.add((n, RDFS.label, Literal(label[:100], lang="en")))
        add_literal(g, n, EDU.name, title)
        add_uri_prop(g, n, EDU.url, url)
        add_literal(g, n, EDU.category, cat)
        add_literal(g, n, EDU.publishedDate, date)
        add_literal(g, n, EDU.body, body[:600] if body else "")
        add_literal(g, n, EDU.scrapedAt, item.get("_scraped_at", ""))
        g.add((n, EDU.belongsTo, inst))
        count += 1

    print(f"     News/Events added: {count}")


def process_student_life(g: Graph, inst: URIRef):
    """Process student_life.json → edu:StudentActivity individuals."""
    print("Processing Student Life")
    data = load_json("student_life.json")
    count = 0

    for item in data:
        cat   = item.get("category", "")
        title = item.get("title", "").strip()
        url   = item.get("url", "").strip()
        body  = item.get("body", "").strip()

        if cat != "student_life" or not title:
            continue

        sa = uri(IIITB, "student_activity", title)
        g.add((sa, RDF.type, EDU.StudentActivity))
        g.add((sa, RDF.type, OWL.NamedIndividual))
        g.add((sa, RDFS.label, Literal(title, lang="en")))
        add_literal(g, sa, EDU.name, title)
        add_uri_prop(g, sa, EDU.url, url)
        add_literal(g, sa, EDU.body, body[:600] if body else "")
        add_literal(g, sa, EDU.scrapedAt, item.get("_scraped_at", ""))

        # Event/club names from headings
        for h in item.get("headings", []):
            if h and h not in ("Quick Links", "Newsletter Sign Up", "Events"):
                add_literal(g, sa, EDU.heading, h)

        g.add((sa, EDU.belongsTo, inst))
        count += 1

    print(f"     Student activities added: {count}")


def process_external(g: Graph, inst: URIRef):
    """Process external.json → edu:ExternalOrg individuals."""
    print("Processing External Organisations")
    data = load_json("external.json")
    count = 0

    for item in data:
        cat   = item.get("category", "")
        title = item.get("title", "").strip()
        url   = item.get("url", "").strip()
        body  = item.get("body", "").strip()

        if cat != "external" or not title:
            continue

        ext = uri(IIITB, "external", title)
        g.add((ext, RDF.type, EDU.ExternalOrg))
        g.add((ext, RDF.type, OWL.NamedIndividual))
        g.add((ext, RDFS.label, Literal(title, lang="en")))
        add_literal(g, ext, EDU.name, title)
        add_uri_prop(g, ext, EDU.url, url)
        add_literal(g, ext, EDU.body, body[:400] if body else "")
        add_literal(g, ext, EDU.scrapedAt, item.get("_scraped_at", ""))
        g.add((inst, EDU.collaboratesWith, ext))
        count += 1

    print(f"     External orgs added: {count}")


# MAIN

def main():
    print("\n" + "="*65)
    print("  IIITB JSON → OWL Converter  (Strategy B — rdflib)")
    print("="*65 + "\n")

    # Build the graph
    g = Graph()
    g.bind("edu",    EDU)
    g.bind("iiitb",  IIITB)
    g.bind("owl",    OWL)
    g.bind("rdfs",   RDFS)
    g.bind("rdf",    RDF)
    g.bind("xsd",    XSD)
    g.bind("foaf",   FOAF)
    g.bind("skos",   SKOS)
    g.bind("schema", SCHEMA)
    g.bind("dc",     DC)

    # TBox (Schema)
    build_tbox(g)

    # ABox (Instances)
    inst = add_institution(g)
    process_faculty(g, inst)
    process_governance(g, inst)
    process_programs(g, inst)
    process_labs(g, inst)
    process_research_scholars(g, inst)
    process_staff(g, inst)
    process_placement(g, inst)
    process_news(g, inst)
    process_student_life(g, inst)
    process_external(g, inst)

    total = len(g)
    print(f"\n Total RDF triples generated: {total}")

    # Serialize
    print("\n Serialising outputs")

    owl_path = OUTPUT_DIR / "iiitb.owl"
    ttl_path = OUTPUT_DIR / "iiitb.ttl"

    # TBox only (for reference)
    g_tbox = Graph()
    g_tbox.bind("edu",  EDU)
    g_tbox.bind("owl",  OWL)
    g_tbox.bind("rdfs", RDFS)
    g_tbox.bind("skos", SKOS)
    g_tbox.bind("schema", SCHEMA)
    tbox_triples = [(s, p, o) for s, p, o in g
                    if (o == OWL.Class or o == OWL.ObjectProperty or o == OWL.DatatypeProperty
                        or p in (RDFS.subClassOf, RDFS.domain, RDFS.range,
                                 OWL.equivalentClass, RDFS.comment, RDFS.label)
                        and str(s).startswith(BASE + "edu"))]
    for t in tbox_triples:
        g_tbox.add(t)
    tbox_path = OUTPUT_DIR / "iiitb_tbox.ttl"
    g_tbox.serialize(str(tbox_path), format="turtle")
    print(f"     TBox written → {tbox_path}  ({len(g_tbox)} triples)")

    # Full OWL (RDF/XML) — open in Protege
    g.serialize(str(owl_path), format="xml")
    print(f"     OWL  written → {owl_path}  ({owl_path.stat().st_size // 1024} KB)")

    # Full Turtle — human-readable
    g.serialize(str(ttl_path), format="turtle")
    print(f"     TTL  written → {ttl_path}  ({ttl_path.stat().st_size // 1024} KB)")

    print("\n" + "="*65)
    print("  DONE!")
    print("  → Open output/iiitb.owl in Protege to browse the ontology.")
    print("  → Load output/iiitb.ttl into Jena Fuseki for SPARQL queries.")
    print("="*65 + "\n")

    # Summary stats
    from collections import Counter
    type_counts = Counter()
    for s, p, o in g:
        if p == RDF.type and o != OWL.NamedIndividual and o != OWL.Class \
                and o != OWL.ObjectProperty and o != OWL.DatatypeProperty \
                and o != OWL.Ontology:
            type_counts[str(o).split("#")[-1].split("/")[-1]] += 1

    print("  Entity Summary:")
    for cls, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        if cnt > 0:
            print(f"    {cls:<25} {cnt:>5} individuals")
    print()


if __name__ == "__main__":
    main()

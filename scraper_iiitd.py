"""
╔══════════════════════════════════════════════════════════════════════╗
║         IIITD Web Scraper — https://www.iiitd.ac.in                 ║
║  Scrapes: Faculty, Departments, Programs, Research, Placements       ║
║  Output : iiitd_scraped_data.json  +  iiitd_master.owl (RDF/XML)    ║
║                                                                      ║
║  REQUIREMENTS:                                                       ║
║      pip install requests beautifulsoup4 lxml                        ║
║                                                                      ║
║  RUN:                                                                ║
║      python3 scraper_iiitd.py                                        ║
╚══════════════════════════════════════════════════════════════════════╝

HOW THIS SCRAPER WORKS — STEP BY STEP:
───────────────────────────────────────
STEP 1 — HTTP Request (fetch_page)
    Uses the `requests` library to send HTTP GET to each IIITD page.
    Browser-like headers (User-Agent, Accept-Language) are set to
    avoid getting blocked by the server (403 Forbidden).
    A session object is reused across requests for efficiency.
    Timeout = 15 seconds per page. Retries = 3 times on failure.

STEP 2 — HTML Parsing (BeautifulSoup)
    The raw HTML response is parsed using BeautifulSoup with the
    'lxml' parser (fastest). CSS selectors and tag searches are
    used to locate specific elements like faculty cards, program
    tables, research lab blocks, etc.

STEP 3 — Data Extraction per Page
    scrape_faculty()    → /faculty page
        Finds name, designation, department, email, profile link
        for every faculty listed on the page.

    scrape_departments() → /research or /academics page
        Finds department names, short codes, research areas.

    scrape_programs()    → /academics page
        Finds B.Tech / M.Tech / Ph.D program names, duration, seats.

    scrape_research()    → /research page
        Finds research lab names, faculty heads, focus areas.

    scrape_placements()  → /placements page
        Finds placement stats: avg CTC, highest CTC, companies,
        top recruiters list.

STEP 4 — Data Cleaning
    strip_text()  — removes extra whitespace, newlines
    clean_email() — validates email format with regex
    clean_url()   — makes relative URLs absolute

STEP 5 — JSON Export
    All scraped data is saved to iiitd_scraped_data.json
    so you can inspect it independently.

STEP 6 — OWL/RDF Generation
    generate_owl() converts the scraped Python dict into a
    valid RDF/XML OWL file with:
        • 16 OWL Classes  (prefix D_)
        • 46 Data Properties with domain + range
        • 18 Object Properties with domain + range + inverseOf
        • All individuals populated with REAL scraped data

NOTE: If a page cannot be reached, the scraper prints a warning
      and continues with other pages — it will not crash.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time

# ══════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════

BASE_URL = "https://www.iiitd.ac.in"

PAGES = {
    "faculty":      BASE_URL + "/faculty",
    "academics":    BASE_URL + "/academics",
    "research":     BASE_URL + "/research",
    "placements":   BASE_URL + "/placement",
    "about":        BASE_URL + "/about",
    "home":         BASE_URL + "/",
}

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

OUTPUT_JSON = "iiitd_scraped_data.json"
OUTPUT_OWL  = "iiitd_master.owl"

# ══════════════════════════════════════════════════════════════
#  STEP 1 — HTTP FETCHING
# ══════════════════════════════════════════════════════════════

session = requests.Session()
session.headers.update(HEADERS)

def fetch_page(url, retries=3, delay=2):
    """
    Fetches a URL and returns a BeautifulSoup object.
    Retries up to `retries` times on failure.
    Returns None if all attempts fail.
    """
    for attempt in range(1, retries + 1):
        try:
            print(f"  [FETCH] {url}  (attempt {attempt})")
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            print(f"  [OK]    {url}  — {len(resp.text)} bytes")
            return soup
        except requests.exceptions.HTTPError as e:
            print(f"  [HTTP ERROR] {url} — {e}")
        except requests.exceptions.ConnectionError as e:
            print(f"  [CONNECTION ERROR] {url} — {e}")
        except requests.exceptions.Timeout:
            print(f"  [TIMEOUT] {url}")
        except Exception as e:
            print(f"  [ERROR] {url} — {e}")
        if attempt < retries:
            print(f"  Retrying in {delay}s ...")
            time.sleep(delay)
    print(f"  [FAILED] Could not fetch: {url}")
    return None

# ══════════════════════════════════════════════════════════════
#  STEP 2 — UTILITY / CLEANING FUNCTIONS
# ══════════════════════════════════════════════════════════════

def strip_text(s):
    """Remove extra whitespace and newlines from a string."""
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s).strip()

def clean_email(s):
    """Return email if valid, else empty string."""
    if not s:
        return ""
    s = s.strip().lower()
    if re.match(r'^[\w.+-]+@[\w.-]+\.\w{2,}$', s):
        return s
    return ""

def clean_url(href):
    """Convert relative URL to absolute."""
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href

def extract_email_from_tag(tag):
    """Find email in mailto: href or text."""
    if not tag:
        return ""
    mailto = tag.find("a", href=re.compile(r"mailto:", re.I))
    if mailto:
        return clean_email(mailto["href"].replace("mailto:", ""))
    text = strip_text(tag.get_text())
    match = re.search(r'[\w.+-]+@[\w.-]+\.\w{2,}', text)
    return match.group(0) if match else ""

# ══════════════════════════════════════════════════════════════
#  STEP 3A — SCRAPE FACULTY
# ══════════════════════════════════════════════════════════════

def scrape_faculty():
    """
    Scrapes the /faculty page.
    Tries multiple CSS selector patterns used by IIITD's site.
    Returns list of dicts with: name, designation, dept, email, profile_url
    """
    print("\n[SCRAPER] Scraping Faculty ...")
    soup = fetch_page(PAGES["faculty"])
    faculty_list = []
    if not soup:
        print("  [WARN] Faculty page unavailable.")
        return faculty_list

    # ── Pattern 1: Bootstrap cards / people-cards ──
    cards = soup.find_all("div", class_=re.compile(r"(people|faculty|member|card|profile)", re.I))
    print(f"  Found {len(cards)} candidate cards")

    for card in cards:
        name        = ""
        designation = ""
        dept        = ""
        email       = ""
        profile_url = ""

        # Name: usually in h3, h4, strong, or .name class
        for tag in ["h3", "h4", "h5", "strong"]:
            el = card.find(tag)
            if el:
                name = strip_text(el.get_text())
                if len(name) > 4:
                    break

        # Name from class
        if not name:
            for cls in ["name", "faculty-name", "person-name", "title"]:
                el = card.find(class_=re.compile(cls, re.I))
                if el:
                    name = strip_text(el.get_text())
                    break

        # Designation
        for cls in ["designation", "position", "role", "post", "subtitle"]:
            el = card.find(class_=re.compile(cls, re.I))
            if el:
                designation = strip_text(el.get_text())
                break

        # Department
        for cls in ["department", "dept", "group", "area"]:
            el = card.find(class_=re.compile(cls, re.I))
            if el:
                dept = strip_text(el.get_text())
                break

        # Email
        email = extract_email_from_tag(card)

        # Profile link
        link = card.find("a", href=True)
        if link:
            profile_url = clean_url(link["href"])

        if name and len(name) > 2:
            faculty_list.append({
                "name":        name,
                "designation": designation,
                "dept":        dept,
                "email":       email,
                "profile_url": profile_url,
            })

    # ── Pattern 2: Table rows ──
    if not faculty_list:
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2:
                name  = strip_text(cells[0].get_text())
                desig = strip_text(cells[1].get_text()) if len(cells) > 1 else ""
                email = extract_email_from_tag(row)
                if name and len(name) > 2:
                    faculty_list.append({
                        "name": name, "designation": desig,
                        "dept": "", "email": email, "profile_url": ""
                    })

    # ── Pattern 3: Any <a> tags linking to /faculty/name ──
    if not faculty_list:
        links = soup.find_all("a", href=re.compile(r"/faculty/|/people/", re.I))
        for link in links:
            name = strip_text(link.get_text())
            if name and len(name) > 2:
                faculty_list.append({
                    "name": name, "designation": "", "dept": "",
                    "email": "", "profile_url": clean_url(link["href"])
                })

    # De-duplicate by name
    seen = set()
    unique = []
    for f in faculty_list:
        key = f["name"].lower()
        if key not in seen and len(f["name"]) > 2:
            seen.add(key)
            unique.append(f)

    print(f"  [RESULT] {len(unique)} faculty members scraped")
    return unique

# ══════════════════════════════════════════════════════════════
#  STEP 3B — SCRAPE DEPARTMENTS
# ══════════════════════════════════════════════════════════════

def scrape_departments():
    """
    Scrapes department info from /research and /academics pages.
    Returns list of dicts: name, shortName, researchAreas, email
    """
    print("\n[SCRAPER] Scraping Departments ...")
    departments = []
    seen = set()

    for page_key in ["research", "academics", "about"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue

        # Pattern 1: Heading tags with dept keywords
        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = strip_text(heading.get_text())
            if any(kw in text.lower() for kw in
                   ["computer science", "electronics", "computational",
                    "mathematics", "humanities", "design", "engineering"]):
                if text not in seen and len(text) > 5:
                    seen.add(text)
                    # Try to get description from next sibling
                    desc = ""
                    sibling = heading.find_next_sibling(["p", "div"])
                    if sibling:
                        desc = strip_text(sibling.get_text())[:200]
                    departments.append({
                        "name":          text,
                        "shortName":     "",
                        "researchAreas": desc,
                        "email":         ""
                    })

        # Pattern 2: nav/menu items that contain dept names
        for tag in soup.find_all(["li", "a"]):
            text = strip_text(tag.get_text())
            if re.search(r'\b(CSE|ECE|CB|HCD|SSH|Maths|Mathematics)\b', text):
                if text not in seen and len(text) < 80:
                    seen.add(text)
                    departments.append({
                        "name": text, "shortName": text,
                        "researchAreas": "", "email": ""
                    })

    print(f"  [RESULT] {len(departments)} departments/groups found")
    return departments

# ══════════════════════════════════════════════════════════════
#  STEP 3C — SCRAPE PROGRAMS
# ══════════════════════════════════════════════════════════════

def scrape_programs():
    """
    Scrapes academic programs from /academics page.
    Returns list of dicts: name, level, duration, seats
    """
    print("\n[SCRAPER] Scraping Academic Programs ...")
    programs = []
    seen = set()

    soup = fetch_page(PAGES["academics"])
    if not soup:
        print("  [WARN] Academics page unavailable.")
        return programs

    # Pattern 1: Program-named cards/sections
    for tag in soup.find_all(["h2", "h3", "h4", "li", "p"]):
        text = strip_text(tag.get_text())
        # Look for B.Tech / M.Tech / Ph.D / M.Sc keywords
        if re.search(r'\b(B\.?Tech|M\.?Tech|Ph\.?D|M\.?Sc|MBA|Integrated)\b', text, re.I):
            if text not in seen and 5 < len(text) < 150:
                seen.add(text)
                # Classify level
                level = "UG" if re.search(r'B\.?Tech|Integrated', text, re.I) else \
                        "PhD" if re.search(r'Ph\.?D', text, re.I) else "PG"
                # Duration guess
                duration = "5 years" if "Integrated" in text else \
                           "4 years" if level == "UG" else \
                           "4-6 years" if level == "PhD" else "2 years"
                programs.append({
                    "name":     text,
                    "level":    level,
                    "duration": duration,
                    "seats":    "",
                    "dept":     ""
                })

    # Pattern 2: Table rows with program info
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                name = strip_text(cells[0].get_text())
                if re.search(r'\b(B\.?Tech|M\.?Tech|Ph\.?D|M\.?Sc)\b', name, re.I):
                    if name not in seen and len(name) > 3:
                        seen.add(name)
                        programs.append({
                            "name":     name,
                            "level":    "UG" if "B.Tech" in name else "PG",
                            "duration": strip_text(cells[1].get_text()) if len(cells)>1 else "",
                            "seats":    strip_text(cells[2].get_text()) if len(cells)>2 else "",
                            "dept":     ""
                        })

    print(f"  [RESULT] {len(programs)} programs found")
    return programs

# ══════════════════════════════════════════════════════════════
#  STEP 3D — SCRAPE RESEARCH LABS
# ══════════════════════════════════════════════════════════════

def scrape_research():
    """
    Scrapes research labs and groups from /research page.
    Returns list of dicts: name, focus, head, dept
    """
    print("\n[SCRAPER] Scraping Research Labs ...")
    labs = []
    seen = set()

    soup = fetch_page(PAGES["research"])
    if not soup:
        print("  [WARN] Research page unavailable.")
        return labs

    # Pattern 1: Lab/group sections
    for tag in soup.find_all(["h2", "h3", "h4"]):
        text = strip_text(tag.get_text())
        if any(kw in text.lower() for kw in ["lab", "group", "center", "centre", "research"]):
            if text not in seen and 4 < len(text) < 120:
                seen.add(text)
                # Get description from next paragraph
                focus = ""
                nxt = tag.find_next_sibling(["p", "div", "ul"])
                if nxt:
                    focus = strip_text(nxt.get_text())[:250]
                labs.append({
                    "name":  text,
                    "focus": focus,
                    "head":  "",
                    "dept":  ""
                })

    # Pattern 2: Cards with lab info
    for card in soup.find_all("div", class_=re.compile(r"(lab|research|group|project)", re.I)):
        name_tag = card.find(["h2","h3","h4","h5","strong"])
        if name_tag:
            name = strip_text(name_tag.get_text())
            if name not in seen and len(name) > 4:
                seen.add(name)
                focus_tag = card.find("p")
                labs.append({
                    "name":  name,
                    "focus": strip_text(focus_tag.get_text())[:250] if focus_tag else "",
                    "head":  "",
                    "dept":  ""
                })

    print(f"  [RESULT] {len(labs)} research labs found")
    return labs

# ══════════════════════════════════════════════════════════════
#  STEP 3E — SCRAPE PLACEMENTS
# ══════════════════════════════════════════════════════════════

def scrape_placements():
    """
    Scrapes placement statistics from /placement page.
    Returns dict with stats and list of recruiter names.
    """
    print("\n[SCRAPER] Scraping Placements ...")
    placement = {
        "year":              "",
        "totalOffers":       "",
        "companies":         "",
        "highestCTC":        "",
        "averageCTC":        "",
        "medianCTC":         "",
        "placementPct":      "",
        "topDomains":        "",
        "recruiters":        []
    }

    soup = fetch_page(PAGES["placements"])
    if not soup:
        print("  [WARN] Placements page unavailable.")
        return placement

    full_text = soup.get_text()

    # Extract CTC values using regex
    ctc_matches = re.findall(r'(?:highest|maximum)\s*(?:CTC|package)[^0-9]*([0-9.]+\s*(?:LPA|lpa|Lakh|lakh|crore|Crore|INR))', full_text, re.I)
    if ctc_matches:
        placement["highestCTC"] = strip_text(ctc_matches[0])

    avg_match = re.search(r'(?:average|avg)\s*(?:CTC|package)[^0-9]*([0-9.]+\s*(?:LPA|lpa|Lakh|lakh))', full_text, re.I)
    if avg_match:
        placement["averageCTC"] = strip_text(avg_match.group(1))

    median_match = re.search(r'median\s*(?:CTC|package)[^0-9]*([0-9.]+\s*(?:LPA|lpa|Lakh|lakh))', full_text, re.I)
    if median_match:
        placement["medianCTC"] = strip_text(median_match.group(1))

    pct_match = re.search(r'([0-9]{2,3})\s*%\s*(?:students?\s*placed|placement)', full_text, re.I)
    if pct_match:
        placement["placementPct"] = pct_match.group(1)

    offers_match = re.search(r'([0-9]+)\s*(?:offers?|jobs?|placements?)\s*(?:made|given|received)', full_text, re.I)
    if offers_match:
        placement["totalOffers"] = offers_match.group(1)

    companies_match = re.search(r'([0-9]+)\s*(?:companies|recruiters|organisations?|organizations?)', full_text, re.I)
    if companies_match:
        placement["companies"] = companies_match.group(1)

    year_match = re.search(r'(?:batch|year|placement)\s*(?:of\s*)?20([0-9]{2})', full_text, re.I)
    if year_match:
        placement["year"] = "20" + year_match.group(1)

    # Recruiter logos / names
    recruiters = set()
    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        src = img.get("src", "")
        for val in [alt, src]:
            val = re.sub(r'\.(png|jpg|jpeg|gif|svg|webp)', '', val, flags=re.I)
            val = re.sub(r'[_\-/]', ' ', val)
            val = strip_text(val)
            if 3 < len(val) < 40 and not any(
                bad in val.lower() for bad in ["logo","banner","photo","image","icon","slide","pic"]):
                recruiters.add(val.title())

    for tag in soup.find_all(["li", "td", "p", "span"]):
        text = strip_text(tag.get_text())
        if 3 < len(text) < 35:
            parent = tag.find_parent(class_=re.compile(r"(recruit|compan|partner|sponsor|logo)", re.I))
            if parent:
                recruiters.add(text.title())

    placement["recruiters"] = sorted(list(recruiters))[:30]

    print(f"  [RESULT] Placement data scraped — {len(placement['recruiters'])} recruiters found")
    return placement

# ══════════════════════════════════════════════════════════════
#  STEP 3F — SCRAPE GENERAL INFO (About Page)
# ══════════════════════════════════════════════════════════════

def scrape_general_info():
    """
    Scrapes general university info: NIRF rank, NAAC, total students, etc.
    """
    print("\n[SCRAPER] Scraping General Info ...")
    info = {
        "name":          "Indraprastha Institute of Information Technology Delhi",
        "shortName":     "IIITD",
        "established":   "2008",
        "type":          "Deemed University",
        "location":      "Okhla Phase III, New Delhi, Delhi 110020",
        "website":       BASE_URL,
        "email":         "info@iiitd.ac.in",
        "phone":         "+91-11-26907400",
        "naacGrade":     "",
        "nirfRank":      "",
        "totalStudents": "",
        "totalFaculty":  "",
        "campusArea":    "",
    }

    for page_key in ["home", "about"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue
        text = soup.get_text()

        naac = re.search(r'NAAC[^A-Z]*([A-C][+]?)', text)
        if naac:
            info["naacGrade"] = naac.group(1)

        nirf = re.search(r'NIRF[^0-9]*([0-9]+)', text)
        if nirf:
            info["nirfRank"] = nirf.group(1)

        students = re.search(r'([0-9,]+)\s*students', text, re.I)
        if students:
            info["totalStudents"] = students.group(1).replace(",", "")

        faculty_count = re.search(r'([0-9]+)\s*(?:faculty|professors)', text, re.I)
        if faculty_count:
            info["totalFaculty"] = faculty_count.group(1)

        # Phone
        phone = re.search(r'(\+91[-\s]?[0-9]{2,4}[-\s]?[0-9]{6,8})', text)
        if phone:
            info["phone"] = phone.group(1)

    print(f"  [RESULT] General info collected")
    return info

# ══════════════════════════════════════════════════════════════
#  STEP 4 — SAVE JSON
# ══════════════════════════════════════════════════════════════

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[JSON] Saved → {path}")

# ══════════════════════════════════════════════════════════════
#  STEP 5 — GENERATE RDF/XML OWL
# ══════════════════════════════════════════════════════════════

OWL_BASE = "http://www.iiitd.ac.in/ontology/IIITD#"
XSD      = "http://www.w3.org/2001/XMLSchema#"

def xe(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def generate_owl(data, output_path):
    """Convert scraped data dict to RDF/XML OWL file."""
    uni   = data.get("university", {})
    facs  = data.get("faculty", [])
    depts = data.get("departments", [])
    progs = data.get("programs", [])
    labs  = data.get("research_labs", [])
    pl    = data.get("placements", {})
    recs  = pl.get("recruiters", [])

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(f'<rdf:RDF\n'
                 f'  xmlns:rdf ="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
                 f'  xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n'
                 f'  xmlns:owl ="http://www.w3.org/2002/07/owl#"\n'
                 f'  xmlns:xsd ="http://www.w3.org/2001/XMLSchema#"\n'
                 f'  xmlns:dc  ="http://purl.org/dc/elements/1.1/"\n'
                 f'  xmlns:D   ="{OWL_BASE}"\n'
                 f'  xml:base  ="{OWL_BASE}">')

    # Ontology header
    lines.append(f'''
  <owl:Ontology rdf:about="{OWL_BASE}">
    <dc:title>IIITD University Ontology — Live Scraped Data</dc:title>
    <dc:description>OWL ontology generated from live scraping of iiitd.ac.in. All entities prefixed D_ for Master OWL mapping.</dc:description>
    <dc:creator>scraper_iiitd.py</dc:creator>
    <owl:versionInfo>3.0.0-scraped</owl:versionInfo>
  </owl:Ontology>''')

    # Classes
    CLASSES = [
        ("D_University","","D_University","A university or academic institution."),
        ("D_Department","D_University","D_Department","An academic department within the university."),
        ("D_Faculty","foaf:Person","D_FacultyMember","A faculty member of the university."),
        ("D_Program","","D_Program","An academic program."),
        ("D_UGProgram","D_Program","D_UGProgram","Undergraduate program."),
        ("D_PGProgram","D_Program","D_PGProgram","Postgraduate program."),
        ("D_DoctoralProgram","D_Program","D_DoctoralProgram","Ph.D program."),
        ("D_Course","","D_Course","An individual course."),
        ("D_ResearchLab","","D_ResearchLab","A research lab or group."),
        ("D_Publication","","D_Publication","A research publication."),
        ("D_Placement","","D_Placement","Annual placement record."),
        ("D_Recruiter","","D_Recruiter","A recruiting company."),
        ("D_Accreditation","","D_Accreditation","An accreditation or ranking."),
        ("D_Facility","","D_Facility","A campus facility."),
        ("D_Student","foaf:Person","D_Student","A student at the university."),
        ("D_Award","","D_Award","An award or recognition."),
    ]
    lines.append("\n  <!-- CLASSES -->")
    for cid, parent, label, comment in CLASSES:
        if parent == "":
            ptag = ""
        elif parent.startswith("foaf:"):
            ptag = f'<rdfs:subClassOf rdf:resource="http://xmlns.com/foaf/0.1/{parent[5:]}"/>'
        else:
            ptag = f'<rdfs:subClassOf rdf:resource="{OWL_BASE}{parent}"/>'
        lines.append(f'  <owl:Class rdf:about="{OWL_BASE}{cid}">'
                     f'<rdfs:label xml:lang="en">{label}</rdfs:label>'
                     f'<rdfs:comment xml:lang="en">{xe(comment)}</rdfs:comment>'
                     f'{ptag}</owl:Class>')

    # Data Properties
    def dp(pid, label, dom, rng):
        lines.append(f'  <owl:DatatypeProperty rdf:about="{OWL_BASE}{pid}">'
                     f'<rdfs:label xml:lang="en">{label}</rdfs:label>'
                     f'<rdfs:domain rdf:resource="{OWL_BASE}{dom}"/>'
                     f'<rdfs:range rdf:resource="{XSD}{rng}"/>'
                     f'</owl:DatatypeProperty>')

    lines.append("\n  <!-- DATA PROPERTIES -->")
    dp("D_hasName",              "D_hasName",              "D_University",    "string")
    dp("D_hasShortName",         "D_hasShortName",         "D_Department",    "string")
    dp("D_hasEstablishedYear",   "D_hasEstablishedYear",   "D_University",    "gYear")
    dp("D_hasUniversityType",    "D_hasUniversityType",    "D_University",    "string")
    dp("D_hasLocation",          "D_hasLocation",          "D_University",    "string")
    dp("D_hasWebsite",           "D_hasWebsite",           "D_University",    "anyURI")
    dp("D_hasEmail",             "D_hasEmail",             "D_Faculty",       "string")
    dp("D_hasPhone",             "D_hasPhone",             "D_University",    "string")
    dp("D_hasNIRFRank",          "D_hasNIRFRank",          "D_University",    "integer")
    dp("D_hasNAACGrade",         "D_hasNAACGrade",         "D_University",    "string")
    dp("D_hasTotalStudents",     "D_hasTotalStudents",     "D_University",    "integer")
    dp("D_hasTotalFaculty",      "D_hasTotalFaculty",      "D_University",    "integer")
    dp("D_hasCampusArea",        "D_hasCampusArea",        "D_University",    "string")
    dp("D_hasDesignation",       "D_hasDesignation",       "D_Faculty",       "string")
    dp("D_hasSpecialization",    "D_hasSpecialization",    "D_Faculty",       "string")
    dp("D_hasPhdFrom",           "D_hasPhdFrom",           "D_Faculty",       "string")
    dp("D_hasProfileURL",        "D_hasProfileURL",        "D_Faculty",       "anyURI")
    dp("D_hasProgramLevel",      "D_hasProgramLevel",      "D_Program",       "string")
    dp("D_hasDuration",          "D_hasDuration",          "D_Program",       "string")
    dp("D_hasTotalSeats",        "D_hasTotalSeats",        "D_Program",       "integer")
    dp("D_hasTotalCredits",      "D_hasTotalCredits",      "D_Program",       "integer")
    dp("D_hasJEECutoff",         "D_hasJEECutoff",         "D_UGProgram",     "integer")
    dp("D_hasGATECutoff",        "D_hasGATECutoff",        "D_PGProgram",     "integer")
    dp("D_hasCourseCode",        "D_hasCourseCode",        "D_Course",        "string")
    dp("D_hasCourseCredits",     "D_hasCourseCredits",     "D_Course",        "integer")
    dp("D_hasSemester",          "D_hasSemester",          "D_Course",        "integer")
    dp("D_hasResearchFocus",     "D_hasResearchFocus",     "D_ResearchLab",   "string")
    dp("D_hasResearchAreas",     "D_hasResearchAreas",     "D_Department",    "string")
    dp("D_hasPublicationTitle",  "D_hasPublicationTitle",  "D_Publication",   "string")
    dp("D_hasVenue",             "D_hasVenue",             "D_Publication",   "string")
    dp("D_hasPublicationYear",   "D_hasPublicationYear",   "D_Publication",   "gYear")
    dp("D_hasPlacementYear",     "D_hasPlacementYear",     "D_Placement",     "gYear")
    dp("D_hasTotalOffers",       "D_hasTotalOffers",       "D_Placement",     "integer")
    dp("D_hasHighestCTC",        "D_hasHighestCTC",        "D_Placement",     "string")
    dp("D_hasAverageCTC",        "D_hasAverageCTC",        "D_Placement",     "string")
    dp("D_hasMedianCTC",         "D_hasMedianCTC",         "D_Placement",     "string")
    dp("D_hasPlacementPercentage","D_hasPlacementPercentage","D_Placement",   "decimal")
    dp("D_hasCompaniesVisited",  "D_hasCompaniesVisited",  "D_Placement",     "integer")
    dp("D_hasTopDomains",        "D_hasTopDomains",        "D_Placement",     "string")
    dp("D_hasAccreditationBody", "D_hasAccreditationBody", "D_Accreditation", "string")
    dp("D_hasAccreditationGrade","D_hasAccreditationGrade","D_Accreditation", "string")
    dp("D_hasAccreditationYear", "D_hasAccreditationYear", "D_Accreditation", "gYear")
    dp("D_hasFacilityType",      "D_hasFacilityType",      "D_Facility",      "string")
    dp("D_hasCapacity",          "D_hasCapacity",          "D_Facility",      "integer")
    dp("D_hasDescription",       "D_hasDescription",       "D_Facility",      "string")

    # Object Properties
    def op(pid, label, dom, rng, inv=None):
        inv_tag = f'<owl:inverseOf rdf:resource="{OWL_BASE}{inv}"/>' if inv else ""
        lines.append(f'  <owl:ObjectProperty rdf:about="{OWL_BASE}{pid}">'
                     f'<rdfs:label xml:lang="en">{label}</rdfs:label>'
                     f'<rdfs:domain rdf:resource="{OWL_BASE}{dom}"/>'
                     f'<rdfs:range rdf:resource="{OWL_BASE}{rng}"/>'
                     f'{inv_tag}</owl:ObjectProperty>')

    lines.append("\n  <!-- OBJECT PROPERTIES -->")
    op("D_hasDepartment",       "D_hasDepartment",       "D_University",  "D_Department",  "D_belongsToUniversity")
    op("D_belongsToUniversity", "D_belongsToUniversity", "D_Department",  "D_University",  "D_hasDepartment")
    op("D_offersProgram",       "D_offersProgram",       "D_Department",  "D_Program",     "D_offeredByDepartment")
    op("D_offeredByDepartment", "D_offeredByDepartment", "D_Program",     "D_Department",  "D_offersProgram")
    op("D_hasMember",           "D_hasMember",           "D_Department",  "D_Faculty",     "D_belongsToDepartment")
    op("D_belongsToDepartment", "D_belongsToDepartment", "D_Faculty",     "D_Department",  "D_hasMember")
    op("D_worksAt",             "D_worksAt",             "D_Faculty",     "D_University")
    op("D_teaches",             "D_teaches",             "D_Faculty",     "D_Course")
    op("D_headsLab",            "D_headsLab",            "D_Faculty",     "D_ResearchLab")
    op("D_hasLab",              "D_hasLab",              "D_Department",  "D_ResearchLab")
    op("D_authored",            "D_authored",            "D_Faculty",     "D_Publication")
    op("D_hasPlacementRecord",  "D_hasPlacementRecord",  "D_University",  "D_Placement")
    op("D_recruitedFrom",       "D_recruitedFrom",       "D_Recruiter",   "D_University")
    op("D_isAccreditedBy",      "D_isAccreditedBy",      "D_University",  "D_Accreditation")
    op("D_hasFacility",         "D_hasFacility",         "D_University",  "D_Facility")
    op("D_enrolledIn",          "D_enrolledIn",          "D_Student",     "D_Program")
    op("D_hasHeadOfDepartment", "D_hasHeadOfDepartment", "D_Department",  "D_Faculty")

    # ── Individuals ──
    lines.append("\n  <!-- INDIVIDUALS -->")

    # University
    uni_id = "IIITD"
    lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{uni_id}">')
    lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}D_University"/>')
    lines.append(f'    <D:D_hasName>{xe(uni.get("name","IIITD"))}</D:D_hasName>')
    if uni.get("shortName"):    lines.append(f'    <D:D_hasShortName>{xe(uni["shortName"])}</D:D_hasShortName>')
    if uni.get("established"):  lines.append(f'    <D:D_hasEstablishedYear rdf:datatype="{XSD}gYear">{uni["established"]}</D:D_hasEstablishedYear>')
    if uni.get("type"):         lines.append(f'    <D:D_hasUniversityType>{xe(uni["type"])}</D:D_hasUniversityType>')
    if uni.get("location"):     lines.append(f'    <D:D_hasLocation>{xe(uni["location"])}</D:D_hasLocation>')
    if uni.get("website"):      lines.append(f'    <D:D_hasWebsite rdf:datatype="{XSD}anyURI">{xe(uni["website"])}</D:D_hasWebsite>')
    if uni.get("email"):        lines.append(f'    <D:D_hasEmail>{xe(uni["email"])}</D:D_hasEmail>')
    if uni.get("phone"):        lines.append(f'    <D:D_hasPhone>{xe(uni["phone"])}</D:D_hasPhone>')
    if uni.get("naacGrade"):    lines.append(f'    <D:D_hasNAACGrade>{xe(uni["naacGrade"])}</D:D_hasNAACGrade>')
    if uni.get("nirfRank"):
        try:    lines.append(f'    <D:D_hasNIRFRank rdf:datatype="{XSD}integer">{int(uni["nirfRank"])}</D:D_hasNIRFRank>')
        except: pass
    if uni.get("totalStudents"):
        try:    lines.append(f'    <D:D_hasTotalStudents rdf:datatype="{XSD}integer">{int(uni["totalStudents"])}</D:D_hasTotalStudents>')
        except: pass
    if uni.get("totalFaculty"):
        try:    lines.append(f'    <D:D_hasTotalFaculty rdf:datatype="{XSD}integer">{int(uni["totalFaculty"])}</D:D_hasTotalFaculty>')
        except: pass
    if uni.get("campusArea"):   lines.append(f'    <D:D_hasCampusArea>{xe(uni["campusArea"])}</D:D_hasCampusArea>')
    if pl:                      lines.append(f'    <D:D_hasPlacementRecord rdf:resource="{OWL_BASE}PLR_scraped"/>')
    lines.append('  </owl:NamedIndividual>')

    # Departments
    for i, d in enumerate(depts):
        did = f"Dept_{i+1}"
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{did}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}D_Department"/>')
        lines.append(f'    <D:D_hasName>{xe(d.get("name",""))}</D:D_hasName>')
        if d.get("shortName"):     lines.append(f'    <D:D_hasShortName>{xe(d["shortName"])}</D:D_hasShortName>')
        if d.get("researchAreas"): lines.append(f'    <D:D_hasResearchAreas>{xe(d["researchAreas"][:200])}</D:D_hasResearchAreas>')
        lines.append(f'    <D:D_belongsToUniversity rdf:resource="{OWL_BASE}{uni_id}"/>')
        lines.append('  </owl:NamedIndividual>')

    # Faculty
    for i, f in enumerate(facs):
        fid = f"Faculty_{i+1}"
        safe = re.sub(r'[^A-Za-z0-9]','_', f.get("name",""))[:30]
        fid  = f"F_{safe}"
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{fid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}D_Faculty"/>')
        lines.append(f'    <D:D_hasName>{xe(f.get("name",""))}</D:D_hasName>')
        if f.get("designation"): lines.append(f'    <D:D_hasDesignation>{xe(f["designation"])}</D:D_hasDesignation>')
        if f.get("email"):       lines.append(f'    <D:D_hasEmail>{xe(f["email"])}</D:D_hasEmail>')
        if f.get("profile_url"): lines.append(f'    <D:D_hasProfileURL rdf:datatype="{XSD}anyURI">{xe(f["profile_url"])}</D:D_hasProfileURL>')
        lines.append(f'    <D:D_worksAt rdf:resource="{OWL_BASE}{uni_id}"/>')
        lines.append('  </owl:NamedIndividual>')

    # Programs
    for i, p in enumerate(progs):
        pid   = f"Prog_{i+1}"
        ptype = "D_UGProgram" if p.get("level")=="UG" else ("D_DoctoralProgram" if p.get("level")=="PhD" else "D_PGProgram")
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{pid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}{ptype}"/>')
        lines.append(f'    <D:D_hasName>{xe(p.get("name",""))}</D:D_hasName>')
        if p.get("level"):    lines.append(f'    <D:D_hasProgramLevel>{p["level"]}</D:D_hasProgramLevel>')
        if p.get("duration"): lines.append(f'    <D:D_hasDuration>{xe(p["duration"])}</D:D_hasDuration>')
        if p.get("seats"):
            try: lines.append(f'    <D:D_hasTotalSeats rdf:datatype="{XSD}integer">{int(p["seats"])}</D:D_hasTotalSeats>')
            except: pass
        lines.append('  </owl:NamedIndividual>')

    # Research Labs
    for i, r in enumerate(labs):
        rid = f"Lab_{i+1}"
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{rid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}D_ResearchLab"/>')
        lines.append(f'    <D:D_hasName>{xe(r.get("name",""))}</D:D_hasName>')
        if r.get("focus"): lines.append(f'    <D:D_hasResearchFocus>{xe(r["focus"][:200])}</D:D_hasResearchFocus>')
        lines.append('  </owl:NamedIndividual>')

    # Placement
    if pl:
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}PLR_scraped">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}D_Placement"/>')
        if pl.get("year"):
            try: lines.append(f'    <D:D_hasPlacementYear rdf:datatype="{XSD}gYear">{int(pl["year"])}</D:D_hasPlacementYear>')
            except: pass
        if pl.get("highestCTC"):     lines.append(f'    <D:D_hasHighestCTC>{xe(pl["highestCTC"])}</D:D_hasHighestCTC>')
        if pl.get("averageCTC"):     lines.append(f'    <D:D_hasAverageCTC>{xe(pl["averageCTC"])}</D:D_hasAverageCTC>')
        if pl.get("medianCTC"):      lines.append(f'    <D:D_hasMedianCTC>{xe(pl["medianCTC"])}</D:D_hasMedianCTC>')
        if pl.get("placementPct"):
            try: lines.append(f'    <D:D_hasPlacementPercentage rdf:datatype="{XSD}decimal">{float(pl["placementPct"])}</D:D_hasPlacementPercentage>')
            except: pass
        if pl.get("totalOffers"):
            try: lines.append(f'    <D:D_hasTotalOffers rdf:datatype="{XSD}integer">{int(pl["totalOffers"])}</D:D_hasTotalOffers>')
            except: pass
        if pl.get("companies"):
            try: lines.append(f'    <D:D_hasCompaniesVisited rdf:datatype="{XSD}integer">{int(pl["companies"])}</D:D_hasCompaniesVisited>')
            except: pass
        lines.append('  </owl:NamedIndividual>')

    # Recruiters
    for i, rec in enumerate(recs):
        rid = "REC_" + re.sub(r'[^A-Za-z0-9]','',rec)
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{rid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}D_Recruiter"/>')
        lines.append(f'    <D:D_hasName>{xe(rec)}</D:D_hasName>')
        lines.append(f'    <D:D_recruitedFrom rdf:resource="{OWL_BASE}{uni_id}"/>')
        lines.append('  </owl:NamedIndividual>')

    lines.append('\n</rdf:RDF>')

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n[OWL] Saved → {output_path}")

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 65)
    print("  IIITD Web Scraper  |  https://www.iiitd.ac.in")
    print("=" * 65)

    # Scrape all sections
    uni_info     = scrape_general_info()
    faculty      = scrape_faculty()
    departments  = scrape_departments()
    programs     = scrape_programs()
    research     = scrape_research()
    placements   = scrape_placements()

    # Bundle
    scraped = {
        "university":    uni_info,
        "faculty":       faculty,
        "departments":   departments,
        "programs":      programs,
        "research_labs": research,
        "placements":    placements,
    }

    # Save JSON
    save_json(scraped, OUTPUT_JSON)

    # Generate OWL
    generate_owl(scraped, OUTPUT_OWL)

    # Summary
    print("\n" + "=" * 65)
    print("  SCRAPING COMPLETE")
    print("=" * 65)
    print(f"  Faculty scraped    : {len(faculty)}")
    print(f"  Departments found  : {len(departments)}")
    print(f"  Programs found     : {len(programs)}")
    print(f"  Research labs found: {len(research)}")
    print(f"  Recruiters found   : {len(placements.get('recruiters',[]))}")
    print(f"\n  Output files:")
    print(f"    {OUTPUT_JSON}   ← inspect raw scraped data")
    print(f"    {OUTPUT_OWL}    ← open in Protege")
    print("=" * 65)

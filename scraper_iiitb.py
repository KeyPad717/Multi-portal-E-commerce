"""
╔══════════════════════════════════════════════════════════════════════╗
║         IIITB Web Scraper — https://www.iiitb.ac.in                 ║
║  Scrapes: Faculty, Departments, Programs, Research, Placements       ║
║  Output : iiitb_scraped_data.json  +  iiitb_master.owl (RDF/XML)    ║
║                                                                      ║
║  REQUIREMENTS:                                                       ║
║      pip install requests beautifulsoup4 lxml                        ║
║                                                                      ║
║  RUN:                                                                ║
║      python3 scraper_iiitb.py                                        ║
╚══════════════════════════════════════════════════════════════════════╝

HOW THIS SCRAPER WORKS — STEP BY STEP:
───────────────────────────────────────
STEP 1 — HTTP Request (fetch_page)
    Uses `requests` with browser-like headers to GET each IIITB page.
    Persistent session object reused for efficiency.
    Retries 3 times with 2-second delay on failure.
    Timeout = 15 seconds.

STEP 2 — HTML Parsing (BeautifulSoup + lxml)
    Raw HTML → BeautifulSoup tree.
    CSS selectors, class-regex matching, tag-name search used to
    locate faculty blocks, program tables, lab sections, etc.

STEP 3 — Data Extraction per Page
    scrape_faculty()     → /faculty and /people pages
        Cards / table rows → name, designation, dept, email, profile_url

    scrape_departments() → /research and /academics pages
        Headings + nav links → dept name, short code, research areas

    scrape_programs()    → /academics and /admissions pages
        Program cards / tables → name, level, duration, seats, cutoff

    scrape_research()    → /research page
        Lab headings + descriptions → lab name, focus, head faculty

    scrape_placements()  → /placements page
        Regex on page text → avg/highest/median CTC, % placed
        Logo images + list items → recruiter company names

    scrape_industry_partners() → /industry-partners or /about page
        Logo alt text + heading links → partner company names

STEP 4 — Cleaning
    strip_text()  — collapses whitespace
    clean_email() — regex validates email format
    clean_url()   — relative → absolute URLs

STEP 5 — JSON export → iiitb_scraped_data.json

STEP 6 — RDF/XML OWL generation → iiitb_master.owl
    18 Classes, 50 Data Properties, 20 Object Properties
    All individuals with B_ prefix labels
    Ready to open in Protege and map into Master OWL
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

BASE_URL = "https://www.iiitb.ac.in"

PAGES = {
    "home":              BASE_URL + "/",
    "faculty":           BASE_URL + "/faculty",
    "people":            BASE_URL + "/people",
    "academics":         BASE_URL + "/academics",
    "admissions":        BASE_URL + "/admissions",
    "research":          BASE_URL + "/research",
    "placements":        BASE_URL + "/placements",
    "industry":          BASE_URL + "/industry-partners",
    "about":             BASE_URL + "/about",
}

HEADERS = {
    "User-Agent":        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36",
    "Accept":            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language":   "en-US,en;q=0.9",
    "Accept-Encoding":   "gzip, deflate, br",
    "Connection":        "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

OUTPUT_JSON = "iiitb_scraped_data.json"
OUTPUT_OWL  = "iiitb_master.owl"

# ══════════════════════════════════════════════════════════════
#  STEP 1 — HTTP FETCHING
# ══════════════════════════════════════════════════════════════

session = requests.Session()
session.headers.update(HEADERS)

def fetch_page(url, retries=3, delay=2):
    """
    Fetches URL and returns BeautifulSoup object.
    Retries up to `retries` times. Returns None on failure.
    """
    for attempt in range(1, retries + 1):
        try:
            print(f"  [FETCH] {url}  (attempt {attempt})")
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            print(f"  [OK]    {url}  — {len(resp.text):,} bytes")
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
    print(f"  [FAILED] {url}")
    return None

# ══════════════════════════════════════════════════════════════
#  STEP 2 — UTILITY / CLEANING
# ══════════════════════════════════════════════════════════════

def strip_text(s):
    if not s:
        return ""
    return re.sub(r'\s+', ' ', str(s)).strip()

def clean_email(s):
    if not s:
        return ""
    s = s.strip().lower()
    if re.match(r'^[\w.+-]+@[\w.-]+\.\w{2,}$', s):
        return s
    return ""

def clean_url(href):
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href

def extract_email_from_tag(tag):
    if not tag:
        return ""
    mailto = tag.find("a", href=re.compile(r"mailto:", re.I))
    if mailto:
        return clean_email(mailto["href"].replace("mailto:", ""))
    text = strip_text(tag.get_text())
    m = re.search(r'[\w.+-]+@[\w.-]+\.\w{2,}', text)
    return m.group(0) if m else ""

# ══════════════════════════════════════════════════════════════
#  STEP 3A — SCRAPE FACULTY
# ══════════════════════════════════════════════════════════════

def scrape_faculty():
    """
    Scrapes /faculty and /people pages.
    Tries Bootstrap cards, div class patterns, and table rows.
    Returns list of dicts: name, designation, dept, email, profile_url
    """
    print("\n[SCRAPER] Scraping Faculty ...")
    faculty_list = []
    seen = set()

    for page_key in ["faculty", "people"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue

        # Pattern 1: div cards with faculty/people/member class
        cards = soup.find_all("div", class_=re.compile(
            r"(faculty|people|member|person|card|profile|team|staff)", re.I))
        print(f"  [{page_key}] {len(cards)} candidate cards")

        for card in cards:
            name = desig = dept = email = profile_url = ""

            # Name: h2/h3/h4/h5/strong or .name/.title class
            for tag in ["h3","h4","h5","h2","strong"]:
                el = card.find(tag)
                if el:
                    t = strip_text(el.get_text())
                    if 3 < len(t) < 80:
                        name = t; break
            if not name:
                for cls in ["name","person-name","faculty-name","title","full-name"]:
                    el = card.find(class_=re.compile(cls, re.I))
                    if el:
                        t = strip_text(el.get_text())
                        if 3 < len(t) < 80:
                            name = t; break

            for cls in ["designation","position","role","post","subtitle","dept-title"]:
                el = card.find(class_=re.compile(cls, re.I))
                if el:
                    desig = strip_text(el.get_text())[:100]; break

            for cls in ["department","dept","group","division","area","affiliation"]:
                el = card.find(class_=re.compile(cls, re.I))
                if el:
                    dept = strip_text(el.get_text())[:80]; break

            email = extract_email_from_tag(card)

            link = card.find("a", href=True)
            if link:
                profile_url = clean_url(link["href"])

            if name and name.lower() not in seen:
                seen.add(name.lower())
                faculty_list.append({
                    "name": name, "designation": desig,
                    "dept": dept, "email": email,
                    "profile_url": profile_url
                })

        # Pattern 2: <tr> rows in a table
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                name  = strip_text(cells[0].get_text())
                desig = strip_text(cells[1].get_text()) if len(cells) > 1 else ""
                email = extract_email_from_tag(row)
                if 3 < len(name) < 80 and name.lower() not in seen:
                    seen.add(name.lower())
                    faculty_list.append({
                        "name": name, "designation": desig,
                        "dept": "", "email": email, "profile_url": ""
                    })

        # Pattern 3: links to /faculty/person-name
        for link in soup.find_all("a", href=re.compile(r"/(faculty|people|person|team)/", re.I)):
            name = strip_text(link.get_text())
            if 3 < len(name) < 80 and name.lower() not in seen:
                seen.add(name.lower())
                faculty_list.append({
                    "name": name, "designation": "", "dept": "",
                    "email": "", "profile_url": clean_url(link["href"])
                })

    print(f"  [RESULT] {len(faculty_list)} faculty scraped")
    return faculty_list

# ══════════════════════════════════════════════════════════════
#  STEP 3B — SCRAPE DEPARTMENTS
# ══════════════════════════════════════════════════════════════

def scrape_departments():
    """
    Scrapes department names and research areas.
    Returns list of dicts: name, shortName, researchAreas, email
    """
    print("\n[SCRAPER] Scraping Departments ...")
    departments = []
    seen = set()

    for page_key in ["research", "academics", "about", "home"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue

        # Headings with dept keywords
        for heading in soup.find_all(["h2","h3","h4"]):
            text = strip_text(heading.get_text())
            if any(kw in text.lower() for kw in [
                "computer science","electronics","computational",
                "mathematics","software","network","data science",
                "information","signal","vlsi","embedded","bioinformatics"]):
                if text not in seen and 5 < len(text) < 100:
                    seen.add(text)
                    desc = ""
                    nxt = heading.find_next_sibling(["p","div"])
                    if nxt:
                        desc = strip_text(nxt.get_text())[:200]
                    # Extract short name
                    short = re.search(r'\b([A-Z]{2,6})\b', text)
                    departments.append({
                        "name":          text,
                        "shortName":     short.group(1) if short else "",
                        "researchAreas": desc,
                        "email":         ""
                    })

        # nav / menu dept labels
        for tag in soup.find_all(["li","a","span"]):
            text = strip_text(tag.get_text())
            if re.search(r'\b(CSA|ECE|DS|CDS|SERC|NETS|VLSI)\b', text):
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
    Scrapes M.Tech / Ph.D / Integrated M.Tech programs.
    Returns list of dicts: name, level, duration, seats
    """
    print("\n[SCRAPER] Scraping Academic Programs ...")
    programs = []
    seen = set()

    for page_key in ["academics", "admissions", "home"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue

        # Headings / list items / paragraphs with program names
        for tag in soup.find_all(["h2","h3","h4","h5","li","p","td"]):
            text = strip_text(tag.get_text())
            if re.search(r'\b(M\.?Tech|M\.?S\.?|Ph\.?D|Integrated|iMTech|MBA|M\.?Sc)\b', text, re.I):
                if text not in seen and 5 < len(text) < 150:
                    seen.add(text)
                    level = "PhD"  if re.search(r'Ph\.?D', text, re.I) else \
                            "UG"   if re.search(r'Integrated|iMTech', text, re.I) else "PG"
                    dur   = "5 years" if level == "UG" else \
                            "4-6 years" if level == "PhD" else "2 years"
                    programs.append({
                        "name": text, "level": level,
                        "duration": dur, "seats": "", "dept": ""
                    })

        # Table rows
        for table in soup.find_all("table"):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td","th"])
                if len(cells) >= 1:
                    name = strip_text(cells[0].get_text())
                    if re.search(r'\b(M\.?Tech|Ph\.?D|M\.?S)\b', name, re.I):
                        if name not in seen and 3 < len(name) < 150:
                            seen.add(name)
                            programs.append({
                                "name": name,
                                "level": "PhD" if "Ph.D" in name else "PG",
                                "duration": strip_text(cells[1].get_text()) if len(cells)>1 else "2 years",
                                "seats": strip_text(cells[2].get_text()) if len(cells)>2 else "",
                                "dept": ""
                            })

    print(f"  [RESULT] {len(programs)} programs found")
    return programs

# ══════════════════════════════════════════════════════════════
#  STEP 3D — SCRAPE RESEARCH LABS
# ══════════════════════════════════════════════════════════════

def scrape_research():
    """
    Scrapes research labs from /research page.
    Returns list of dicts: name, focus, head, dept
    """
    print("\n[SCRAPER] Scraping Research Labs ...")
    labs = []
    seen = set()

    soup = fetch_page(PAGES["research"])
    if not soup:
        print("  [WARN] Research page unavailable.")
        return labs

    # Headings with lab/group keywords
    for tag in soup.find_all(["h2","h3","h4","h5"]):
        text = strip_text(tag.get_text())
        if any(kw in text.lower() for kw in
               ["lab","group","center","centre","research","project","initiative"]):
            if text not in seen and 4 < len(text) < 120:
                seen.add(text)
                focus = ""
                nxt = tag.find_next_sibling(["p","div","ul"])
                if nxt:
                    focus = strip_text(nxt.get_text())[:250]
                labs.append({"name": text, "focus": focus, "head": "", "dept": ""})

    # div cards with lab class
    for card in soup.find_all("div", class_=re.compile(r"(lab|research|group|project|center)", re.I)):
        name_tag = card.find(["h2","h3","h4","h5","strong"])
        if name_tag:
            name = strip_text(name_tag.get_text())
            if name not in seen and 4 < len(name) < 120:
                seen.add(name)
                fp = card.find("p")
                labs.append({
                    "name":  name,
                    "focus": strip_text(fp.get_text())[:250] if fp else "",
                    "head":  "", "dept": ""
                })

    print(f"  [RESULT] {len(labs)} research labs found")
    return labs

# ══════════════════════════════════════════════════════════════
#  STEP 3E — SCRAPE PLACEMENTS
# ══════════════════════════════════════════════════════════════

def scrape_placements():
    """
    Scrapes placement stats and recruiter list from /placements page.
    """
    print("\n[SCRAPER] Scraping Placements ...")
    placement = {
        "year": "", "totalOffers": "", "companies": "",
        "highestCTC": "", "averageCTC": "", "medianCTC": "",
        "placementPct": "", "topDomains": "", "recruiters": []
    }

    soup = fetch_page(PAGES["placements"])
    if not soup:
        print("  [WARN] Placements page unavailable.")
        return placement

    text = soup.get_text()

    # CTC extraction
    h_ctc = re.search(r'(?:highest|maximum|best)\s*(?:CTC|package|salary)[^0-9]*([0-9.]+\s*(?:LPA|lpa|Lakh|Crore|INR|crore))', text, re.I)
    if h_ctc: placement["highestCTC"] = strip_text(h_ctc.group(1))

    a_ctc = re.search(r'(?:average|avg|mean)\s*(?:CTC|package|salary)[^0-9]*([0-9.]+\s*(?:LPA|lpa|Lakh|lakh))', text, re.I)
    if a_ctc: placement["averageCTC"] = strip_text(a_ctc.group(1))

    m_ctc = re.search(r'median\s*(?:CTC|package|salary)[^0-9]*([0-9.]+\s*(?:LPA|lpa|Lakh|lakh))', text, re.I)
    if m_ctc: placement["medianCTC"] = strip_text(m_ctc.group(1))

    pct = re.search(r'([0-9]{2,3})\s*%\s*(?:students?\s*placed|placement)', text, re.I)
    if pct: placement["placementPct"] = pct.group(1)

    offers = re.search(r'([0-9]{2,4})\s*(?:offers?|jobs?)\s*(?:made|given|total)', text, re.I)
    if offers: placement["totalOffers"] = offers.group(1)

    cos = re.search(r'([0-9]{2,4})\s*(?:companies|recruiters|organisations?)', text, re.I)
    if cos: placement["companies"] = cos.group(1)

    yr = re.search(r'(?:batch|placement|class)\s*(?:of\s*)?20([0-9]{2})', text, re.I)
    if yr: placement["year"] = "20" + yr.group(1)

    # Recruiter names from img alt or logo sections
    recruiters = set()
    logo_sections = soup.find_all(class_=re.compile(r"(recruit|compan|partner|sponsor|logo|client)", re.I))
    for section in logo_sections:
        for img in section.find_all("img"):
            alt = strip_text(img.get("alt",""))
            if 2 < len(alt) < 40 and not any(
                b in alt.lower() for b in ["logo","photo","banner","image","slide","icon"]):
                recruiters.add(alt.title())
        for tag in section.find_all(["li","span","p","td"]):
            t = strip_text(tag.get_text())
            if 2 < len(t) < 35:
                recruiters.add(t.title())

    # Broader image alt scan
    for img in soup.find_all("img"):
        alt = strip_text(img.get("alt",""))
        src = img.get("src","")
        val = alt if alt else re.sub(r'\.(png|jpg|jpeg|gif|svg|webp)','', os.path.basename(src), flags=re.I)
        val = re.sub(r'[_\-]',' ', val)
        val = strip_text(val)
        if 2 < len(val) < 35 and not any(
            b in val.lower() for b in ["logo","photo","banner","image","slide","icon","iiitb","campus"]):
            recruiters.add(val.title())

    placement["recruiters"] = sorted(list(recruiters))[:30]
    print(f"  [RESULT] Placement data scraped — {len(placement['recruiters'])} recruiters found")
    return placement

# ══════════════════════════════════════════════════════════════
#  STEP 3F — SCRAPE INDUSTRY PARTNERS
# ══════════════════════════════════════════════════════════════

def scrape_industry_partners():
    """
    Scrapes industry partner names from /industry-partners and /about.
    Returns list of dicts: name, type
    """
    print("\n[SCRAPER] Scraping Industry Partners ...")
    partners = []
    seen = set()

    for page_key in ["industry", "about", "home"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue

        # Sections labelled industry / partner / sponsor
        for section in soup.find_all(class_=re.compile(
                r"(industry|partner|sponsor|associate|collaborat)", re.I)):
            for img in section.find_all("img"):
                name = strip_text(img.get("alt",""))
                if 2 < len(name) < 50 and name.lower() not in seen:
                    seen.add(name.lower())
                    partners.append({"name": name.title(), "type": "Industry Partner"})
            for tag in section.find_all(["h3","h4","li","strong","a"]):
                name = strip_text(tag.get_text())
                if 2 < len(name) < 50 and name.lower() not in seen:
                    seen.add(name.lower())
                    partners.append({"name": name.title(), "type": "Industry Partner"})

        # Headings that mention partner names
        for h in soup.find_all(["h3","h4","h5"]):
            text = strip_text(h.get_text())
            parent = h.find_parent(class_=re.compile(r"(partner|industry|sponsor)", re.I))
            if parent and text.lower() not in seen and 2 < len(text) < 50:
                seen.add(text.lower())
                partners.append({"name": text.title(), "type": "Industry Partner"})

    print(f"  [RESULT] {len(partners)} industry partners found")
    return partners

# ══════════════════════════════════════════════════════════════
#  STEP 3G — SCRAPE GENERAL INFO
# ══════════════════════════════════════════════════════════════

def scrape_general_info():
    """Scrapes NIRF, NAAC, student/faculty counts from home and about pages."""
    print("\n[SCRAPER] Scraping General Info ...")
    info = {
        "name":          "International Institute of Information Technology Bangalore",
        "shortName":     "IIITB",
        "established":   "1999",
        "type":          "Deemed University Public-Private Partnership",
        "location":      "26/C Electronics City Hosur Road Bengaluru Karnataka 560100",
        "website":       BASE_URL,
        "email":         "info@iiitb.ac.in",
        "phone":         "+91-80-41401661",
        "naacGrade":     "",
        "nirfRank":      "",
        "totalStudents": "",
        "totalFaculty":  "",
        "campusArea":    "",
    }

    for page_key in ["home","about"]:
        soup = fetch_page(PAGES[page_key])
        if not soup:
            continue
        text = soup.get_text()

        naac  = re.search(r'NAAC[^A-Z]*([A-C][+]?)', text)
        if naac:  info["naacGrade"] = naac.group(1)

        nirf  = re.search(r'NIRF[^0-9]*([0-9]+)', text)
        if nirf:  info["nirfRank"] = nirf.group(1)

        stud  = re.search(r'([0-9,]+)\s*students', text, re.I)
        if stud:  info["totalStudents"] = stud.group(1).replace(",","")

        fac   = re.search(r'([0-9]+)\s*(?:faculty|professors|faculties)', text, re.I)
        if fac:   info["totalFaculty"] = fac.group(1)

        phone = re.search(r'(\+91[-\s]?[0-9]{2,4}[-\s]?[0-9]{6,8})', text)
        if phone: info["phone"] = phone.group(1)

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
#  STEP 5 — GENERATE RDF/XML OWL (B_ prefix)
# ══════════════════════════════════════════════════════════════

OWL_BASE = "http://www.iiitb.ac.in/ontology/IIITB#"
XSD      = "http://www.w3.org/2001/XMLSchema#"

def xe(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def generate_owl(data, output_path):
    uni      = data.get("university", {})
    facs     = data.get("faculty", [])
    depts    = data.get("departments", [])
    progs    = data.get("programs", [])
    labs     = data.get("research_labs", [])
    pl       = data.get("placements", {})
    recs     = pl.get("recruiters", [])
    partners = data.get("industry_partners", [])

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(f'<rdf:RDF\n'
                 f'  xmlns:rdf ="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
                 f'  xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n'
                 f'  xmlns:owl ="http://www.w3.org/2002/07/owl#"\n'
                 f'  xmlns:xsd ="http://www.w3.org/2001/XMLSchema#"\n'
                 f'  xmlns:dc  ="http://purl.org/dc/elements/1.1/"\n'
                 f'  xmlns:B   ="{OWL_BASE}"\n'
                 f'  xml:base  ="{OWL_BASE}">')

    lines.append(f'''
  <owl:Ontology rdf:about="{OWL_BASE}">
    <dc:title>IIITB University Ontology — Live Scraped Data</dc:title>
    <dc:description>OWL ontology generated from live scraping of iiitb.ac.in. All entities prefixed B_ for Master OWL mapping.</dc:description>
    <dc:creator>scraper_iiitb.py</dc:creator>
    <owl:versionInfo>3.0.0-scraped</owl:versionInfo>
  </owl:Ontology>''')

    # Classes
    CLASSES = [
        ("B_University",      "",            "B_University",        "A university or academic institution."),
        ("B_Department",      "B_University","B_Department",        "An academic department."),
        ("B_Faculty",         "foaf:Person", "B_FacultyMember",     "A faculty member of IIITB."),
        ("B_Program",         "",            "B_Program",           "An academic program."),
        ("B_UGProgram",       "B_Program",   "B_UGProgram",         "Undergraduate level program."),
        ("B_PGProgram",       "B_Program",   "B_PGProgram",         "Postgraduate level program."),
        ("B_DoctoralProgram", "B_Program",   "B_DoctoralProgram",   "Ph.D research program."),
        ("B_Course",          "",            "B_Course",            "An individual course or subject."),
        ("B_ResearchLab",     "",            "B_ResearchLab",       "A research lab or group."),
        ("B_Publication",     "",            "B_Publication",       "A research publication."),
        ("B_Placement",       "",            "B_Placement",         "Annual placement record."),
        ("B_Recruiter",       "",            "B_Recruiter",         "A company that recruits students."),
        ("B_Accreditation",   "",            "B_Accreditation",     "An accreditation or ranking."),
        ("B_Facility",        "",            "B_Facility",          "A campus facility."),
        ("B_IndustryPartner", "",            "B_IndustryPartner",   "An industry partner."),
        ("B_Student",         "foaf:Person", "B_Student",           "A student at the university."),
        ("B_Award",           "",            "B_Award",             "An award or recognition."),
        ("B_ResearchProject", "",            "B_ResearchProject",   "A funded research project."),
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
    dp("B_hasName",               "B_hasName",               "B_University",    "string")
    dp("B_hasShortName",          "B_hasShortName",          "B_Department",    "string")
    dp("B_hasEstablishedYear",    "B_hasEstablishedYear",    "B_University",    "gYear")
    dp("B_hasUniversityType",     "B_hasUniversityType",     "B_University",    "string")
    dp("B_hasLocation",           "B_hasLocation",           "B_University",    "string")
    dp("B_hasWebsite",            "B_hasWebsite",            "B_University",    "anyURI")
    dp("B_hasEmail",              "B_hasEmail",              "B_Faculty",       "string")
    dp("B_hasPhone",              "B_hasPhone",              "B_University",    "string")
    dp("B_hasNIRFRank",           "B_hasNIRFRank",           "B_University",    "integer")
    dp("B_hasNAACGrade",          "B_hasNAACGrade",          "B_University",    "string")
    dp("B_hasTotalStudents",      "B_hasTotalStudents",      "B_University",    "integer")
    dp("B_hasTotalFaculty",       "B_hasTotalFaculty",       "B_University",    "integer")
    dp("B_hasCampusArea",         "B_hasCampusArea",         "B_University",    "string")
    dp("B_hasVision",             "B_hasVision",             "B_University",    "string")
    dp("B_hasDesignation",        "B_hasDesignation",        "B_Faculty",       "string")
    dp("B_hasSpecialization",     "B_hasSpecialization",     "B_Faculty",       "string")
    dp("B_hasPhdFrom",            "B_hasPhdFrom",            "B_Faculty",       "string")
    dp("B_hasProfileURL",         "B_hasProfileURL",         "B_Faculty",       "anyURI")
    dp("B_hasResearchAreas",      "B_hasResearchAreas",      "B_Department",    "string")
    dp("B_hasProgramLevel",       "B_hasProgramLevel",       "B_Program",       "string")
    dp("B_hasDuration",           "B_hasDuration",           "B_Program",       "string")
    dp("B_hasTotalSeats",         "B_hasTotalSeats",         "B_Program",       "integer")
    dp("B_hasTotalCredits",       "B_hasTotalCredits",       "B_Program",       "integer")
    dp("B_hasJEECutoff",          "B_hasJEECutoff",          "B_UGProgram",     "integer")
    dp("B_hasGATECutoff",         "B_hasGATECutoff",         "B_PGProgram",     "integer")
    dp("B_hasCourseCode",         "B_hasCourseCode",         "B_Course",        "string")
    dp("B_hasCourseCredits",      "B_hasCourseCredits",      "B_Course",        "integer")
    dp("B_hasSemester",           "B_hasSemester",           "B_Course",        "integer")
    dp("B_hasResearchFocus",      "B_hasResearchFocus",      "B_ResearchLab",   "string")
    dp("B_hasPublicationTitle",   "B_hasPublicationTitle",   "B_Publication",   "string")
    dp("B_hasVenue",              "B_hasVenue",              "B_Publication",   "string")
    dp("B_hasPublicationYear",    "B_hasPublicationYear",    "B_Publication",   "gYear")
    dp("B_hasPlacementYear",      "B_hasPlacementYear",      "B_Placement",     "gYear")
    dp("B_hasTotalOffers",        "B_hasTotalOffers",        "B_Placement",     "integer")
    dp("B_hasHighestCTC",         "B_hasHighestCTC",         "B_Placement",     "string")
    dp("B_hasAverageCTC",         "B_hasAverageCTC",         "B_Placement",     "string")
    dp("B_hasMedianCTC",          "B_hasMedianCTC",          "B_Placement",     "string")
    dp("B_hasPlacementPercentage","B_hasPlacementPercentage","B_Placement",     "decimal")
    dp("B_hasCompaniesVisited",   "B_hasCompaniesVisited",   "B_Placement",     "integer")
    dp("B_hasTopDomains",         "B_hasTopDomains",         "B_Placement",     "string")
    dp("B_hasAccreditationBody",  "B_hasAccreditationBody",  "B_Accreditation", "string")
    dp("B_hasAccreditationGrade", "B_hasAccreditationGrade", "B_Accreditation", "string")
    dp("B_hasAccreditationYear",  "B_hasAccreditationYear",  "B_Accreditation", "gYear")
    dp("B_hasFacilityType",       "B_hasFacilityType",       "B_Facility",      "string")
    dp("B_hasCapacity",           "B_hasCapacity",           "B_Facility",      "integer")
    dp("B_hasDescription",        "B_hasDescription",        "B_Facility",      "string")
    dp("B_hasPartnerType",        "B_hasPartnerType",        "B_IndustryPartner","string")

    # Object Properties
    def op(pid, label, dom, rng, inv=None):
        inv_tag = f'<owl:inverseOf rdf:resource="{OWL_BASE}{inv}"/>' if inv else ""
        lines.append(f'  <owl:ObjectProperty rdf:about="{OWL_BASE}{pid}">'
                     f'<rdfs:label xml:lang="en">{label}</rdfs:label>'
                     f'<rdfs:domain rdf:resource="{OWL_BASE}{dom}"/>'
                     f'<rdfs:range rdf:resource="{OWL_BASE}{rng}"/>'
                     f'{inv_tag}</owl:ObjectProperty>')

    lines.append("\n  <!-- OBJECT PROPERTIES -->")
    op("B_hasDepartment",        "B_hasDepartment",        "B_University",     "B_Department",     "B_belongsToUniversity")
    op("B_belongsToUniversity",  "B_belongsToUniversity",  "B_Department",     "B_University",     "B_hasDepartment")
    op("B_offersProgram",        "B_offersProgram",        "B_Department",     "B_Program",        "B_offeredByDepartment")
    op("B_offeredByDepartment",  "B_offeredByDepartment",  "B_Program",        "B_Department",     "B_offersProgram")
    op("B_hasMember",            "B_hasMember",            "B_Department",     "B_Faculty",        "B_belongsToDepartment")
    op("B_belongsToDepartment",  "B_belongsToDepartment",  "B_Faculty",        "B_Department",     "B_hasMember")
    op("B_hasHeadOfDepartment",  "B_hasHeadOfDepartment",  "B_Department",     "B_Faculty")
    op("B_worksAt",              "B_worksAt",              "B_Faculty",        "B_University")
    op("B_teaches",              "B_teaches",              "B_Faculty",        "B_Course")
    op("B_headsLab",             "B_headsLab",             "B_Faculty",        "B_ResearchLab")
    op("B_hasLab",               "B_hasLab",               "B_Department",     "B_ResearchLab")
    op("B_authored",             "B_authored",             "B_Faculty",        "B_Publication")
    op("B_hasPlacementRecord",   "B_hasPlacementRecord",   "B_University",     "B_Placement")
    op("B_recruitedFrom",        "B_recruitedFrom",        "B_Recruiter",      "B_University")
    op("B_isAccreditedBy",       "B_isAccreditedBy",       "B_University",     "B_Accreditation")
    op("B_hasFacility",          "B_hasFacility",          "B_University",     "B_Facility")
    op("B_hasIndustryPartner",   "B_hasIndustryPartner",   "B_University",     "B_IndustryPartner")
    op("B_enrolledIn",           "B_enrolledIn",           "B_Student",        "B_Program")
    op("B_courseOfferedIn",      "B_courseOfferedIn",      "B_Course",         "B_Program")
    op("B_fundedBy",             "B_fundedBy",             "B_ResearchProject","B_IndustryPartner")

    # ── Individuals ──
    lines.append("\n  <!-- INDIVIDUALS -->")
    uni_id = "IIITB"

    # University
    lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{uni_id}">')
    lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_University"/>')
    lines.append(f'    <B:B_hasName>{xe(uni.get("name","IIITB"))}</B:B_hasName>')
    if uni.get("shortName"):    lines.append(f'    <B:B_hasShortName>{xe(uni["shortName"])}</B:B_hasShortName>')
    if uni.get("established"):  lines.append(f'    <B:B_hasEstablishedYear rdf:datatype="{XSD}gYear">{uni["established"]}</B:B_hasEstablishedYear>')
    if uni.get("type"):         lines.append(f'    <B:B_hasUniversityType>{xe(uni["type"])}</B:B_hasUniversityType>')
    if uni.get("location"):     lines.append(f'    <B:B_hasLocation>{xe(uni["location"])}</B:B_hasLocation>')
    if uni.get("website"):      lines.append(f'    <B:B_hasWebsite rdf:datatype="{XSD}anyURI">{uni["website"]}</B:B_hasWebsite>')
    if uni.get("email"):        lines.append(f'    <B:B_hasEmail>{xe(uni["email"])}</B:B_hasEmail>')
    if uni.get("phone"):        lines.append(f'    <B:B_hasPhone>{xe(uni["phone"])}</B:B_hasPhone>')
    if uni.get("naacGrade"):    lines.append(f'    <B:B_hasNAACGrade>{xe(uni["naacGrade"])}</B:B_hasNAACGrade>')
    if uni.get("nirfRank"):
        try:    lines.append(f'    <B:B_hasNIRFRank rdf:datatype="{XSD}integer">{int(uni["nirfRank"])}</B:B_hasNIRFRank>')
        except: pass
    if uni.get("totalStudents"):
        try:    lines.append(f'    <B:B_hasTotalStudents rdf:datatype="{XSD}integer">{int(uni["totalStudents"])}</B:B_hasTotalStudents>')
        except: pass
    if uni.get("totalFaculty"):
        try:    lines.append(f'    <B:B_hasTotalFaculty rdf:datatype="{XSD}integer">{int(uni["totalFaculty"])}</B:B_hasTotalFaculty>')
        except: pass
    if pl: lines.append(f'    <B:B_hasPlacementRecord rdf:resource="{OWL_BASE}B_PLR_scraped"/>')
    lines.append('  </owl:NamedIndividual>')

    # Departments
    for i, d in enumerate(depts):
        did = f"B_Dept_{i+1}"
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{did}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_Department"/>')
        lines.append(f'    <B:B_hasName>{xe(d.get("name",""))}</B:B_hasName>')
        if d.get("shortName"):     lines.append(f'    <B:B_hasShortName>{xe(d["shortName"])}</B:B_hasShortName>')
        if d.get("researchAreas"): lines.append(f'    <B:B_hasResearchAreas>{xe(d["researchAreas"][:200])}</B:B_hasResearchAreas>')
        lines.append(f'    <B:B_belongsToUniversity rdf:resource="{OWL_BASE}{uni_id}"/>')
        lines.append('  </owl:NamedIndividual>')

    # Faculty
    for i, f in enumerate(facs):
        safe = re.sub(r'[^A-Za-z0-9]','_', f.get("name",""))[:30]
        fid  = f"B_F_{safe}"
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{fid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_Faculty"/>')
        lines.append(f'    <B:B_hasName>{xe(f.get("name",""))}</B:B_hasName>')
        if f.get("designation"): lines.append(f'    <B:B_hasDesignation>{xe(f["designation"])}</B:B_hasDesignation>')
        if f.get("email"):       lines.append(f'    <B:B_hasEmail>{xe(f["email"])}</B:B_hasEmail>')
        if f.get("dept"):        lines.append(f'    <B:B_hasSpecialization>{xe(f["dept"])}</B:B_hasSpecialization>')
        if f.get("profile_url"): lines.append(f'    <B:B_hasProfileURL rdf:datatype="{XSD}anyURI">{xe(f["profile_url"])}</B:B_hasProfileURL>')
        lines.append(f'    <B:B_worksAt rdf:resource="{OWL_BASE}{uni_id}"/>')
        lines.append('  </owl:NamedIndividual>')

    # Programs
    for i, p in enumerate(progs):
        pid   = f"B_Prog_{i+1}"
        ptype = "B_UGProgram" if p.get("level")=="UG" else \
                ("B_DoctoralProgram" if p.get("level")=="PhD" else "B_PGProgram")
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{pid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}{ptype}"/>')
        lines.append(f'    <B:B_hasName>{xe(p.get("name",""))}</B:B_hasName>')
        if p.get("level"):    lines.append(f'    <B:B_hasProgramLevel>{p["level"]}</B:B_hasProgramLevel>')
        if p.get("duration"): lines.append(f'    <B:B_hasDuration>{xe(p["duration"])}</B:B_hasDuration>')
        if p.get("seats"):
            try: lines.append(f'    <B:B_hasTotalSeats rdf:datatype="{XSD}integer">{int(p["seats"])}</B:B_hasTotalSeats>')
            except: pass
        lines.append('  </owl:NamedIndividual>')

    # Research Labs
    for i, r in enumerate(labs):
        rid = f"B_Lab_{i+1}"
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{rid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_ResearchLab"/>')
        lines.append(f'    <B:B_hasName>{xe(r.get("name",""))}</B:B_hasName>')
        if r.get("focus"): lines.append(f'    <B:B_hasResearchFocus>{xe(r["focus"][:200])}</B:B_hasResearchFocus>')
        lines.append('  </owl:NamedIndividual>')

    # Placement
    if pl:
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}B_PLR_scraped">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_Placement"/>')
        if pl.get("year"):
            try: lines.append(f'    <B:B_hasPlacementYear rdf:datatype="{XSD}gYear">{int(pl["year"])}</B:B_hasPlacementYear>')
            except: pass
        if pl.get("highestCTC"):  lines.append(f'    <B:B_hasHighestCTC>{xe(pl["highestCTC"])}</B:B_hasHighestCTC>')
        if pl.get("averageCTC"):  lines.append(f'    <B:B_hasAverageCTC>{xe(pl["averageCTC"])}</B:B_hasAverageCTC>')
        if pl.get("medianCTC"):   lines.append(f'    <B:B_hasMedianCTC>{xe(pl["medianCTC"])}</B:B_hasMedianCTC>')
        if pl.get("placementPct"):
            try: lines.append(f'    <B:B_hasPlacementPercentage rdf:datatype="{XSD}decimal">{float(pl["placementPct"])}</B:B_hasPlacementPercentage>')
            except: pass
        if pl.get("totalOffers"):
            try: lines.append(f'    <B:B_hasTotalOffers rdf:datatype="{XSD}integer">{int(pl["totalOffers"])}</B:B_hasTotalOffers>')
            except: pass
        if pl.get("companies"):
            try: lines.append(f'    <B:B_hasCompaniesVisited rdf:datatype="{XSD}integer">{int(pl["companies"])}</B:B_hasCompaniesVisited>')
            except: pass
        lines.append('  </owl:NamedIndividual>')

    # Recruiters
    for rec in recs:
        rid = "B_REC_" + re.sub(r'[^A-Za-z0-9]','',rec)
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{rid}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_Recruiter"/>')
        lines.append(f'    <B:B_hasName>{xe(rec)}</B:B_hasName>')
        lines.append(f'    <B:B_recruitedFrom rdf:resource="{OWL_BASE}{uni_id}"/>')
        lines.append('  </owl:NamedIndividual>')

    # Industry Partners
    for i, ip in enumerate(partners):
        pid2 = "B_IP_" + re.sub(r'[^A-Za-z0-9]','',ip["name"])[:20]
        lines.append(f'  <owl:NamedIndividual rdf:about="{OWL_BASE}{pid2}">')
        lines.append(f'    <rdf:type rdf:resource="{OWL_BASE}B_IndustryPartner"/>')
        lines.append(f'    <B:B_hasName>{xe(ip["name"])}</B:B_hasName>')
        lines.append(f'    <B:B_hasPartnerType>{xe(ip.get("type","Industry Partner"))}</B:B_hasPartnerType>')
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
    print("  IIITB Web Scraper  |  https://www.iiitb.ac.in")
    print("=" * 65)

    uni_info     = scrape_general_info()
    faculty      = scrape_faculty()
    departments  = scrape_departments()
    programs     = scrape_programs()
    research     = scrape_research()
    placements   = scrape_placements()
    partners     = scrape_industry_partners()

    scraped = {
        "university":         uni_info,
        "faculty":            faculty,
        "departments":        departments,
        "programs":           programs,
        "research_labs":      research,
        "placements":         placements,
        "industry_partners":  partners,
    }

    save_json(scraped, OUTPUT_JSON)
    generate_owl(scraped, OUTPUT_OWL)

    print("\n" + "=" * 65)
    print("  SCRAPING COMPLETE")
    print("=" * 65)
    print(f"  Faculty scraped     : {len(faculty)}")
    print(f"  Departments found   : {len(departments)}")
    print(f"  Programs found      : {len(programs)}")
    print(f"  Research labs found : {len(research)}")
    print(f"  Recruiters found    : {len(placements.get('recruiters',[]))}")
    print(f"  Industry partners   : {len(partners)}")
    print(f"\n  Output files:")
    print(f"    {OUTPUT_JSON}   ← inspect raw scraped data")
    print(f"    {OUTPUT_OWL}    ← open in Protege")
    print("=" * 65)

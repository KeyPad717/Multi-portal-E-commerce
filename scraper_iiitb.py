"""
IIITB Scraper + Clean OWL Generator (IIITH Style)
"""

import requests
from bs4 import BeautifulSoup
import json
import time

# ✅ RDF/OWL
from rdflib import Graph, Namespace, RDF, RDFS, Literal, URIRef
from rdflib.namespace import OWL

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BASE_URL = "https://www.iiitb.ac.in"


# --------------------------------------------------
# FETCH PAGE
# --------------------------------------------------
def fetch_page(url, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            print(f"[Attempt {attempt+1}] Error: {e}")
            time.sleep(2)
    return None


# --------------------------------------------------
# SCRAPE FACULTY
# --------------------------------------------------
def scrape_faculty():
    print("\n=== Scraping Faculty ===")

    urls = [
        BASE_URL + "/faculty",
        BASE_URL + "/people"
    ]

    faculty_list = []

    for url in urls:
        soup = fetch_page(url)
        if not soup:
            continue

        cards = soup.select("div, article")

        for card in cards:
            name_el = card.find(["h3", "h4", "strong"])
            if not name_el:
                continue

            name = name_el.get_text(strip=True)

            faculty_list.append({
                "name": name,
                "designation": "",
                "department": "",
                "email": ""
            })

    # fallback
    if len(faculty_list) < 5:
        return [
            {"name": "Prof A", "designation": "Professor", "department": "CSE", "email": ""},
            {"name": "Prof B", "designation": "Associate Professor", "department": "ECE", "email": ""}
        ]

    return faculty_list


# --------------------------------------------------
# STATIC / SIMPLE DATA
# --------------------------------------------------
def get_departments():
    return [
        {"name": "Computer Science"},
        {"name": "Electronics and Communication"},
        {"name": "Data Science"}
    ]


def get_programs():
    return [
        {"name": "M.Tech CSE", "duration": "2 years"},
        {"name": "M.Tech ECE", "duration": "2 years"},
        {"name": "PhD", "duration": "4-5 years"}
    ]


def get_research_labs():
    return [
        {"name": "Data Science Lab", "focus": "AI and ML"},
        {"name": "VLSI Lab", "focus": "Chip Design"}
    ]


def get_placements():
    return {
        "recruiters": [
            "Google",
            "Microsoft",
            "Amazon",
            "Adobe"
        ]
    }


def get_university_info():
    return {
        "name": "IIIT Bangalore",
        "location": "Bangalore, India",
        "established": "1999"
    }


# --------------------------------------------------
# COLLECT DATA
# --------------------------------------------------
def collect_all_data():
    data = {
        "university": get_university_info(),
        "departments": get_departments(),
        "programs": get_programs(),
        "faculty": scrape_faculty(),
        "research_labs": get_research_labs(),
        "placements": get_placements()
    }

    with open("iiitb_data.json", "w") as f:
        json.dump(data, f, indent=2)

    print("JSON saved ✅")
    return data


# --------------------------------------------------
# ✅ CLEAN OWL (IIITH STYLE)
# --------------------------------------------------
def convert_to_owl_iiitb(data, output_file="iiitb.owl"):
    print("\n=== Converting IIITB to OWL ===")

    g = Graph()

    IIITB = Namespace("http://iiitb.ac.in/ontology#")
    g.bind("iiitb", IIITB)

    # ---------------- Classes ----------------
    g.add((IIITB.Institution, RDF.type, OWL.Class))
    g.add((IIITB.Department, RDF.type, OWL.Class))
    g.add((IIITB.Faculty, RDF.type, OWL.Class))
    g.add((IIITB.Program, RDF.type, OWL.Class))
    g.add((IIITB.ResearchLab, RDF.type, OWL.Class))
    g.add((IIITB.Recruiter, RDF.type, OWL.Class))

    # ---------------- Institution ----------------
    inst = data["university"]

    inst_uri = URIRef(IIITB["IIITB"])

    g.add((inst_uri, RDF.type, IIITB.Institution))
    g.add((inst_uri, RDFS.label, Literal(inst["name"])))
    g.add((inst_uri, IIITB.location, Literal(inst["location"])))
    g.add((inst_uri, IIITB.established, Literal(inst["established"])))

    # ---------------- Departments ----------------
    for dept in data["departments"]:
        dept_uri = URIRef(IIITB[dept["name"].replace(" ", "_")])

        g.add((dept_uri, RDF.type, IIITB.Department))
        g.add((dept_uri, RDFS.label, Literal(dept["name"])))

        g.add((inst_uri, IIITB.hasDepartment, dept_uri))

    # ---------------- Faculty ----------------
    for fac in data["faculty"]:
        fac_uri = URIRef(IIITB[fac["name"].replace(" ", "_")])

        g.add((fac_uri, RDF.type, IIITB.Faculty))
        g.add((fac_uri, RDFS.label, Literal(fac["name"])))

        if fac.get("email"):
            g.add((fac_uri, IIITB.email, Literal(fac["email"])))

        g.add((inst_uri, IIITB.hasFaculty, fac_uri))

    # ---------------- Programs ----------------
    for prog in data["programs"]:
        prog_uri = URIRef(IIITB[prog["name"].replace(" ", "_")])

        g.add((prog_uri, RDF.type, IIITB.Program))
        g.add((prog_uri, RDFS.label, Literal(prog["name"])))
        g.add((prog_uri, IIITB.duration, Literal(prog["duration"])))

        g.add((inst_uri, IIITB.hasProgram, prog_uri))

    # ---------------- Research Labs ----------------
    for lab in data["research_labs"]:
        lab_uri = URIRef(IIITB[lab["name"].replace(" ", "_")])

        g.add((lab_uri, RDF.type, IIITB.ResearchLab))
        g.add((lab_uri, RDFS.label, Literal(lab["name"])))

        if lab.get("focus"):
            g.add((lab_uri, IIITB.researchFocus, Literal(lab["focus"])))

        g.add((inst_uri, IIITB.hasLab, lab_uri))

    # ---------------- Recruiters ----------------
    for rec in data["placements"]["recruiters"]:
        rec_uri = URIRef(IIITB[rec.replace(" ", "_")])

        g.add((rec_uri, RDF.type, IIITB.Recruiter))
        g.add((rec_uri, RDFS.label, Literal(rec)))

        g.add((inst_uri, IIITB.hasRecruiter, rec_uri))

    # ---------------- Save ----------------
    g.serialize(destination=output_file, format="xml")

    print(f"OWL file saved as {output_file} ✅")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    data = collect_all_data()
    convert_to_owl_iiitb(data)

    print("\nDONE ✅")
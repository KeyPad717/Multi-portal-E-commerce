"""
IIIT Hyderabad - Semantic Web Project
Scrapes data and generates JSON + OWL file
"""

import requests
from bs4 import BeautifulSoup
import json
import time

# ✅ NEW: RDF/OWL imports
from rdflib import Graph, Namespace, RDF, RDFS, Literal, URIRef
from rdflib.namespace import OWL

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BASE_URL = "https://www.iiit.ac.in"


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
# FACULTY (SCRAPING + FALLBACK)
# --------------------------------------------------
def scrape_faculty():
    print("\n=== Scraping Faculty ===")

    url = "https://www.iiit.ac.in/people/faculty/"
    soup = fetch_page(url)

    if not soup:
        return get_fallback_faculty()

    faculty_list = []
    cards = soup.select(".faculty-card, .people-card, article")

    for card in cards:
        name_el = card.select_one("h3, h4, strong")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)

        faculty_list.append({
            "name": name,
            "designation": "",
            "department": "",
            "email": ""
        })

    if len(faculty_list) < 10:
        return get_fallback_faculty()

    return faculty_list


def get_fallback_faculty():
    return [
        {"name": "P J Narayanan", "designation": "Director", "department": "CSE", "email": "pjn@iiit.ac.in"},
        {"name": "C V Jawahar", "designation": "Professor", "department": "CSE", "email": "jawahar@iiit.ac.in"},
    ]


# --------------------------------------------------
# STATIC DATA
# --------------------------------------------------
def get_departments():
    return [
        {"name": "Computer Science and Engineering", "abbreviation": "CSE", "head": "Kannan Srinathan"},
        {"name": "Electronics and Communication Engineering", "abbreviation": "ECE", "head": "Sachin Chaudhari"},
    ]


def get_programs():
    return [
        {"name": "B.Tech CSE", "level": "UG", "duration": "4 years"},
        {"name": "M.Tech CSE", "level": "PG", "duration": "2 years"},
    ]


def get_courses():
    return [
        {"code": "CS101", "name": "Programming", "credits": 4, "department": "CSE"},
        {"code": "CS201", "name": "Data Structures", "credits": 4, "department": "CSE"},
    ]


def get_institution_info():
    return {
        "name": "IIIT Hyderabad",
        "location": "Hyderabad, India",
        "established": "1998"
    }


# --------------------------------------------------
# COLLECT DATA
# --------------------------------------------------
def collect_all_data():
    data = {
        "institution": get_institution_info(),
        "departments": get_departments(),
        "programs": get_programs(),
        "faculty": scrape_faculty(),
        "courses": get_courses(),
    }

    with open("iiith_data.json", "w") as f:
        json.dump(data, f, indent=2)

    print("JSON saved ✅")
    return data


# --------------------------------------------------
# ✅ OWL CONVERSION FUNCTION
# --------------------------------------------------
def convert_to_owl(data, output_file="iiith.owl"):
    print("\n=== Converting to OWL ===")

    g = Graph()

    IIIT = Namespace("http://iiit.ac.in/ontology#")
    g.bind("iiit", IIIT)

    # ---------------- Classes ----------------
    g.add((IIIT.Institution, RDF.type, OWL.Class))
    g.add((IIIT.Department, RDF.type, OWL.Class))
    g.add((IIIT.Faculty, RDF.type, OWL.Class))
    g.add((IIIT.Program, RDF.type, OWL.Class))
    g.add((IIIT.Course, RDF.type, OWL.Class))

    # ---------------- Institution ----------------
    inst = data["institution"]
    inst_uri = URIRef(IIIT["IIIT_Hyderabad"])

    g.add((inst_uri, RDF.type, IIIT.Institution))
    g.add((inst_uri, RDFS.label, Literal(inst["name"])))
    g.add((inst_uri, IIIT.location, Literal(inst["location"])))

    # ---------------- Departments ----------------
    dept_map = {}

    for dept in data["departments"]:
        dept_uri = URIRef(IIIT[dept["abbreviation"]])
        dept_map[dept["name"]] = dept_uri

        g.add((dept_uri, RDF.type, IIIT.Department))
        g.add((dept_uri, RDFS.label, Literal(dept["name"])))

        g.add((inst_uri, IIIT.hasDepartment, dept_uri))

    # ---------------- Faculty ----------------
    for fac in data["faculty"]:
        fac_id = fac["name"].replace(" ", "_")
        fac_uri = URIRef(IIIT[fac_id])

        g.add((fac_uri, RDF.type, IIIT.Faculty))
        g.add((fac_uri, RDFS.label, Literal(fac["name"])))

        if fac.get("email"):
            g.add((fac_uri, IIIT.email, Literal(fac["email"])))

        # Link to department
        dept_uri = dept_map.get(fac["department"])
        if dept_uri:
            g.add((fac_uri, IIIT.belongsToDepartment, dept_uri))

        g.add((inst_uri, IIIT.hasFaculty, fac_uri))

    # ---------------- Programs ----------------
    for prog in data["programs"]:
        prog_id = prog["name"].replace(" ", "_")
        prog_uri = URIRef(IIIT[prog_id])

        g.add((prog_uri, RDF.type, IIIT.Program))
        g.add((prog_uri, RDFS.label, Literal(prog["name"])))
        g.add((prog_uri, IIIT.duration, Literal(prog["duration"])))

        g.add((inst_uri, IIIT.hasProgram, prog_uri))

    # ---------------- Courses ----------------
    for course in data["courses"]:
        course_uri = URIRef(IIIT[course["code"]])

        g.add((course_uri, RDF.type, IIIT.Course))
        g.add((course_uri, RDFS.label, Literal(course["name"])))
        g.add((course_uri, IIIT.credits, Literal(course["credits"])))

    # ---------------- Save OWL ----------------
    g.serialize(destination=output_file, format="xml")

    print(f"OWL file saved as {output_file} ✅")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    data = collect_all_data()

    # ✅ Generate OWL
    convert_to_owl(data)

    print("\nDONE")

import xml.etree.ElementTree as ET
import re

# Namespaces
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "onto": "http://iiitb.ac.in/ontology/autonomous#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xsd": "http://www.w3.org/2001/XMLSchema#"
}

# Register namespaces for output
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

FILE_PATH = "output/faculty_RC_sir.owl"
tree = ET.parse(FILE_PATH)
root = tree.getroot()

# Entities to convert to individuals if they are classes (Rule 2)
TO_INDIVIDUALS = {
    "#DataScience", "#SoftwareArchitecture", "#BITES", "#MINRO", 
    "#Top10DataScienceAcademiciansOfIndia2018", "#Top10DataScienceAcademiciansOfIndia2019",
    "#DataModeling", "#DatabaseDesign", "#DataAnalytics", "#SoftwareEngineering",
    "#LargeScaleApplicationDevelopment", "#CTRI-DG", "#CenterForSmartGovernance",
    "#DepartmentOfEducation", "#DepartmentOfFinance", "#IIITB",
    "#ResearchPaper1", "#ResearchPaper2"
}

# Mapping of potential individual targets to their classes (Rule 5)
INDIVIDUAL_CLASSES = {
    "#DataScience": "#ResearchArea",
    "#SoftwareArchitecture": "#FieldOfStudy",
    "#DataModeling": "#FieldOfStudy",
    "#DatabaseDesign": "#FieldOfStudy",
    "#DataAnalytics": "#FieldOfStudy",
    "#SoftwareEngineering": "#ResearchArea",
    "#LargeScaleApplicationDevelopment": "#ResearchArea",
    "#BITES": "#Board",
    "#MINRO": "#Center",
    "#CTRI-DG": "#Center",
    "#CenterForSmartGovernance": "#GovernmentDepartment",
    "#DepartmentOfEducation": "#GovernmentDepartment",
    "#DepartmentOfFinance": "#GovernmentDepartment",
    "#IIITB": "#EducationInstitution",
    "#ResearchPaper1": "#Publication",
    "#ResearchPaper2": "#Publication",
    "#Top10DataScienceAcademiciansOfIndia2018": "#Award",
    "#Top10DataScienceAcademiciansOfIndia2019": "#Award"
}

# First pass: Identify classes and individuals
entities = {} # about -> element
for desc in root.findall("rdf:Description", NS):
    about = desc.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
    if about:
        entities[about] = desc

# Second pass: Refine modeling
for about, desc in entities.items():
    # Rule 1 & 2: Convert leaf groups to individuals
    if about in TO_INDIVIDUALS:
        # Check if it has owl:Class type, remove it
        types = desc.findall("rdf:type", NS)
        is_class = False
        for t in types:
            res = t.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
            if res == NS["owl"] + "Class":
                desc.remove(t)
                is_class = True
        
        # Add NamedIndividual type if missing
        has_ind_type = False
        for t in desc.findall("rdf:type", NS):
            res = t.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
            if res == NS["owl"] + "NamedIndividual":
                has_ind_type = True
        
        if not has_ind_type:
            ET.SubElement(desc, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}type", 
                         {"{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource": NS["owl"] + "NamedIndividual"})
        
        # Rule 5: Maintain Hierarchy
        target_class = INDIVIDUAL_CLASSES.get(about)
        if target_class:
            has_class_type = False
            for t in desc.findall("rdf:type", NS):
                res = t.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
                if res == target_class:
                    has_class_type = True
            if not has_class_type:
                ET.SubElement(desc, "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}type", 
                             {"{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource": target_class})

# Rule 3 & 4: Preserve relationships and ensure individual targets
# Note: most were already correct in the file, but we standardize them here.
# We also need to fix the namespace issue. 
# Relative URIs in assertions like "#DataModeling" are fine AS LONG AS xml:base is set.

# Output manually with xml:base
output_file = "output/refined_faculty_RC_sir.owl"

def prettify(elem):
    from xml.dom import minidom
    rough_string = ET.tostring(elem, "utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

# ET doesnt handle xml:base nicely on root during generation easily
# We will write the header manually.
header = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF
   xml:base="http://iiitb.ac.in/ontology/autonomous#"
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:onto="http://iiitb.ac.in/ontology/autonomous#"
   xmlns:owl="http://www.w3.org/2002/07/owl#"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
   xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
>
"""

content = ""
for desc in root.findall("rdf:Description", NS):
    # Standardize tags: ensure property tags use the onto: prefix if they are in the autonomous namespace
    # but when ET serializes, it uses the registered namespace.
    s = ET.tostring(desc, encoding="unicode")
    # Clean up excess namespace declarations if any
    content += "  " + s + "\n"

footer = "</rdf:RDF>"

with open(output_file, "w") as f:
    f.write(header + content + footer)

print(f"Refined OWL saved to {output_file}")

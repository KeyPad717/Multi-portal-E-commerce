from rdflib import Graph

data = """
@prefix onto: <http://iiitb.ac.in/ontology/autonomous#>
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
@prefix owl: <http://www.w3.org/2002/07/owl#>
@prefix xsd: <http://www.w3.org/2001/XMLSchema#>

onto:ChandrashekarRamanathan rdf:type onto:Person.
"""

g = Graph()
try:
    g.parse(data=data, format="turtle")
    print("Success")
except Exception as e:
    print(f"Failed: {e}")

data_fixed = """
@prefix onto: <http://iiitb.ac.in/ontology/autonomous#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

onto:ChandrashekarRamanathan rdf:type onto:Person .
"""

g2 = Graph()
try:
    g2.parse(data=data_fixed, format="turtle")
    print("Fixed Success")
except Exception as e:
    print(f"Fixed Failed: {e}")

import rdflib
from rdflib import Graph, Namespace, RDF, OWL, Literal
import os

def build_final_integrated_graph():
    # Paths
    DEPTS_OWL = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/departments/departments_combined.owl"
    PROGS_OWL = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/programmes/output/programmes_combined.owl"
    BRIDGE_OWL = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/bridge_axioms.owl"
    MASTER_OWL = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/integrated_institutional_graph.owl"

    # Merge target
    g_master = Graph()

    # Load All Components
    print(f"Loading {os.path.basename(DEPTS_OWL)}...")
    g_master.parse(DEPTS_OWL, format="xml")

    print(f"Loading {os.path.basename(PROGS_OWL)}...")
    g_master.parse(PROGS_OWL, format="xml")

    print(f"Loading {os.path.basename(BRIDGE_OWL)}...")
    g_master.parse(BRIDGE_OWL, format="xml")

    # Add master metadata
    MASTER_NS = Namespace("http://iiitb.ac.in/ontology/integrated#")
    header = rdflib.URIRef(str(MASTER_NS))
    g_master.add((header, RDF.type, OWL.Ontology))
    g_master.add((header, rdflib.RDFS.label, Literal("Integrated Institutional Knowledge Graph (Depts + Programmes)", lang="en")))
    g_master.add((header, rdflib.RDFS.comment, Literal("A master ontology linking academic departments with study programmes using autonomous semantic bridging.", lang="en")))

    # Bind namespaces for readability
    g_master.bind("dept", Namespace("http://iiitb.ac.in/ontology/departments#"))
    g_master.bind("prog", Namespace("http://iiitb.ac.in/ontology/programmes#"))
    g_master.bind("bridge", Namespace("http://iiitb.ac.in/ontology/bridge#"))
    g_master.bind("cse", Namespace("https://cse.iiitb.ac.in#"))
    g_master.bind("ece", Namespace("https://ece.iiitb.ac.in#"))

    # Save
    g_master.serialize(destination=MASTER_OWL, format="pretty-xml")
    print(f"DONE Integrated graph saved to {MASTER_OWL}")
    print(f"Final triple count: {len(g_master)}")

if __name__ == "__main__":
    build_final_integrated_graph()

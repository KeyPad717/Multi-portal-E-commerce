from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, OWL
from master_schema import OntologyData
import urllib.parse

def generate_owl(ontology_data: OntologyData, output_file: str = "output.owl"):
    """
    Takes valid OntologyData triples and compiles them into a valid OWL format.
    """
    g = Graph()
    
    # Define our custom namespaces
    UNI = Namespace("http://www.example.org/university#")
    g.bind("uni", UNI)
    g.bind("owl", OWL)
    
    # Define basic ontology metadata
    g.add((UNI.UniversityOntology, RDF.type, OWL.Ontology))
    
    # Generate the triples inside the graph
    for triple in ontology_data.triples:
        # Create safe URIs from subjects and objects
        subj_uri_str = urllib.parse.quote(triple.subject.replace(" ", "_"))
        obj_uri_str = urllib.parse.quote(triple.object.replace(" ", "_"))
        
        subj_uri = URIRef(UNI[subj_uri_str])
        obj_uri = URIRef(UNI[obj_uri_str])
        
        # To make it semantically richer, we assume subjects are NamedIndividuals 
        # (in a real scenario, you'd have the LLM dictate if it's a Class or Individual)
        g.add((subj_uri, RDF.type, OWL.NamedIndividual))
        
        # If the predicate is "teachesCourse", it's an ObjectProperty
        pred_uri = URIRef(UNI[triple.predicate])
        g.add((pred_uri, RDF.type, OWL.ObjectProperty))
        
        # Add the actual relationship
        g.add((subj_uri, pred_uri, obj_uri))

    # Serialize to OWL/XML format
    print(f"Serializing graph to {output_file}...")
    g.serialize(destination=output_file, format='xml')
    print("Done!")

if __name__ == "__main__":
    from master_schema import Triple
    sample_data = OntologyData(triples=[
        Triple(subject="Prof. Sadagopan", predicate="teachesCourse", object="Data Structures")
    ])
    generate_owl(sample_data, "test_output.owl")

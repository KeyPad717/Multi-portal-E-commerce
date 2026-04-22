import rdflib
from rdflib import Graph, RDF, RDFS, OWL
import json
import os

def extract_ontology_signature(owl_path):
    """
    Extracts Classes, ObjectProperties, DatatypeProperties, and key Individuals
    from an OWL file to provide a summary for the LLM.
    """
    g = Graph()
    try:
        g.parse(owl_path, format="xml")
    except Exception as e:
        # Fallback to turtle if xml fails
        try:
            g.parse(owl_path, format="turtle")
        except Exception as e2:
            return {"error": f"Failed to parse {owl_path}: {e2}"}

    signature = {
        "classes": [],
        "object_properties": [],
        "datatype_properties": [],
        "individuals_sample": []
    }

    # Extract Classes
    for s in g.subjects(RDF.type, OWL.Class):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        signature["classes"].append({
            "uri": str(s),
            "label": str(label) if label else "",
            "comment": str(comment) if comment else ""
        })

    # Extract Object Properties
    for s in g.subjects(RDF.type, OWL.ObjectProperty):
        label = g.value(s, RDFS.label)
        domain = g.value(s, RDFS.domain)
        range_ = g.value(s, RDFS.range)

        # Grounding: Sample up to 3 triples
        examples = []
        count = 0
        for subj, obj in g.subject_objects(s):
            if count >= 3: break
            s_types = [str(t).split('#')[-1] for t in g.objects(subj, RDF.type) if str(t) != str(OWL.NamedIndividual)]
            o_types = [str(t).split('#')[-1] for t in g.objects(obj, RDF.type) if str(t) != str(OWL.NamedIndividual)]
            examples.append({
                "from_class": s_types[0] if s_types else "Unknown",
                "to_class": o_types[0] if o_types else "Unknown"
            })
            count += 1

        signature["object_properties"].append({
            "uri": str(s),
            "label": str(label) if label else "",
            "domain": str(domain).split('#')[-1] if domain else "Thing",
            "range": str(range_).split('#')[-1] if range_ else "Thing",
            "examples": examples
        })

    # Extract Datatype Properties
    for s in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = g.value(s, RDFS.label)
        
        # Grounding: Sample up to 3 literals
        examples = []
        count = 0
        for subj, lit in g.subject_objects(s):
            if count >= 3: break
            s_types = [str(t).split('#')[-1] for t in g.objects(subj, RDF.type) if str(t) != str(OWL.NamedIndividual)]
            examples.append({
                "from_class": s_types[0] if s_types else "Unknown",
                "value": str(lit)[:100] # truncate long strings
            })
            count += 1

        signature["datatype_properties"].append({
            "uri": str(s),
            "label": str(label) if label else "",
            "examples": examples
        })

    # Extract Individuals (Sample of 15)
    inds = list(g.subjects(RDF.type, OWL.NamedIndividual))
    for s in inds[:15]:
        label = g.value(s, RDFS.label)
        types = [str(t) for t in g.objects(s, RDF.type) if str(t) != str(OWL.NamedIndividual)]
        signature["individuals_sample"].append({
            "uri": str(s),
            "label": str(label) if label else "",
            "types": types
        })

    return signature

def main():
    depts_owl = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/departments/departments_combined.owl"
    progs_owl = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/programmes/output/programmes_combined.owl"
    output_json = "/home/iiitb/Desktop/Semantic-Integration-of-Institutional-Data/bridge_signatures.json"

    print(f"Extracting signature from: {os.path.basename(depts_owl)}")
    dept_sig = extract_ontology_signature(depts_owl)

    print(f"Extracting signature from: {os.path.basename(progs_owl)}")
    prog_sig = extract_ontology_signature(progs_owl)

    total_sig = {
        "departments": dept_sig,
        "programmes": prog_sig
    }

    with open(output_json, "w") as f:
        json.dump(total_sig, f, indent=2)
    
    print(f"✅ Signatures saved to {output_json}")

if __name__ == "__main__":
    main()

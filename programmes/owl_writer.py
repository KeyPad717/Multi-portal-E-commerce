"""
owl_writer.py -- Serialize the rdflib Graph to OWL/XML and Turtle.
The .owl (RDF/XML) file can be opened directly in Protégé.
The .ttl (Turtle) file is human-readable for debugging.
"""

import os
from rdflib import Graph

# Ontology base URI -- must match triple_builder.BASE_URI
OWL_BASE = "http://iiitb.ac.in/ontology/autonomous#"


def _patch_rdf_header(owl_path: str) -> None:
    with open(owl_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Only patch if xml:base is absent (idempotent)
    if "xml:base" not in content:
        content = content.replace(
            "<rdf:RDF\n",
            f'<rdf:RDF\n   xml:base="{OWL_BASE}"\n'
        )

    # Ensure xmlns:xsd is present (rdflib may drop it when no typed
    # literals survive serialization, but range declarations reference it)
    if "xmlns:xsd" not in content:
        content = content.replace(
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
            '   xmlns:xsd="http://www.w3.org/2001/XMLSchema#"'
        )

    with open(owl_path, "w", encoding="utf-8") as f:
        f.write(content)


def save_owl(g: Graph,
             base_path: str = "output/faculty_RC_sir") -> str:
    """
    Save the graph in two formats:
    - RDF/XML (.owl) -- for Protégé
    - Turtle (.ttl) -- human-readable
    Returns path to the .owl file.
    """
    os.makedirs(os.path.dirname(base_path)
                if os.path.dirname(base_path) else ".",
                exist_ok=True)

    owl_path    = base_path + ".owl"
    turtle_path = base_path + ".ttl"

    # RDF/XML (Protégé native format)
    g.serialize(destination=owl_path, format="xml")
    _patch_rdf_header(owl_path)          # inject xml:base + xmlns:xsd
    owl_size = os.path.getsize(owl_path) / 1024

    # Turtle (human-readable)   
    g.serialize(destination=turtle_path, format="turtle")
    ttl_size = os.path.getsize(turtle_path) / 1024

    print(f"\n  [owl_writer] ✓ OWL/XML  → {owl_path} "
          f"({owl_size:.1f} KB)")
    print(f"  [owl_writer] ✓ Turtle   → {turtle_path} "
          f"({ttl_size:.1f} KB)")
    print(f"  [owl_writer] Total triples: {len(g)}")

    return owl_path

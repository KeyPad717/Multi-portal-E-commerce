"""
owl_writer.py — Serialize the rdflib Graph to OWL/XML and Turtle.
The .owl (RDF/XML) file can be opened directly in Protégé.
The .ttl (Turtle) file is human-readable for debugging.
"""

import os
from rdflib import Graph


def save_owl(g: Graph,
             base_path: str = "output/faculty_RC") -> str:
    """
    Save the graph in two formats:
    - RDF/XML (.owl) — for Protégé
    - Turtle (.ttl) — human-readable
    Returns path to the .owl file.
    """
    os.makedirs(os.path.dirname(base_path)
                if os.path.dirname(base_path) else ".",
                exist_ok=True)

    owl_path    = base_path + ".owl"
    turtle_path = base_path + ".ttl"

    # ── RDF/XML (Protégé native format) ──────────────────
    g.serialize(destination=owl_path, format="xml")
    owl_size = os.path.getsize(owl_path) / 1024

    # ── Turtle (human-readable) ───────────────────────────
    g.serialize(destination=turtle_path, format="turtle")
    ttl_size = os.path.getsize(turtle_path) / 1024

    print(f"\n  [owl_writer] ✓ OWL/XML  → {owl_path} "
          f"({owl_size:.1f} KB)")
    print(f"  [owl_writer] ✓ Turtle   → {turtle_path} "
          f"({ttl_size:.1f} KB)")
    print(f"  [owl_writer] Total triples: {len(g)}")

    return owl_path

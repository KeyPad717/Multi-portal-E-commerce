from pydantic import BaseModel, Field
from typing import List, Literal

class Triple(BaseModel):
    subject: str = Field(description="The source entity, e.g., 'Prof. Sadagopan' or 'Data Structures'")
    predicate: str = Field(description="The relationship between subject and object formatted in camelCase (e.g., 'teachesCourse', 'isPrerequisiteFor', 'hasPlacementRate', 'admitsStudents').")
    object: str = Field(description="The target entity, e.g., 'IIIT Bangalore', 'Machine Learning', or 'CS101'")

class OntologyData(BaseModel):
    triples: List[Triple] = Field(description="List of extracted semantic triples representing the ontology.")

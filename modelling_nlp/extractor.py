import os
import json
from groq import Groq
from master_schema import OntologyData

def extract_triples(text: str) -> OntologyData:
    """
    Takes raw text, sends it to Groq API with instructions to extract 
    triples strictly conforming to the OntologyData schema, and returns the parsed schema.
    """
    client = Groq(api_key="GROQ_API_KEY")
    schema_json = OntologyData.model_json_schema()
    
    system_prompt = f"""
    You are an expert Semantic Web extraction pipeline. 
    Your job is to read raw text content from university web pages and extract semantic relationships (triples).
    
    You MUST output valid JSON that strictly conforms to the following JSON Schema:
    {json.dumps(schema_json, indent=2)}
    
    Important Constraints:
    - Invent descriptive camelCase predicates for the semantic relationships you identify when appropriate.
    - Keep Subject and Object concise (e.g., "Prof. John Doe", "Computer Science", "Placement Cell").
    - Try to extract up to 15 highly confident triples from the text.
    - Output ONLY the JSON object, nothing else.
    """

    # We might need to chunk text if it's too long, but for the PoC we assume text is reasonably sized.
    # Llama-3.3 has a large context window, so we truncate roughly to 20000 chars for safety.
    max_chars = 20000
    if len(text) > max_chars:
        text = text[:max_chars]

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract triples from the following text:\n\n{text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        json_output = response.choices[0].message.content
        data = json.loads(json_output)
        
        # Validate against our Pydantic model
        validated_data = OntologyData(**data)
        return validated_data
        
    except Exception as e:
        print(f"Error during LLM extraction: {e}")
        return OntologyData(triples=[])

if __name__ == "__main__":
    sample_text = "Prof. Sadagopan teaches Data Structures at IIIT Bangalore. He is a member of the Computer Science Department."
    print("Testing extraction on sample text...")
    result = extract_triples(sample_text)
    print(result.model_dump_json(indent=2))

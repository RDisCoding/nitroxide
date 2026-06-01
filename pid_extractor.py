import os
import sys
import json
import base64
from pathlib import Path

# Load config
current_dir = Path(__file__).resolve().parent
PID_GRAPH_PATH = str(current_dir / "pid_graph_state.json")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def _load_groq_client():
    try:
        from groq import Groq
    except Exception as exc:
        raise RuntimeError("Groq SDK is not installed. Install the 'groq' package first.") from exc

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY. Put it in the .env file or environment.")
    return Groq(api_key=api_key)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_pid_to_graph(image_path):
    print(f"Reading image: {image_path}")
    if not os.path.exists(image_path):
        print(f"Error: Image {image_path} not found.")
        return

    # Determine mime type
    mime_type = "image/jpeg"
    if image_path.lower().endswith(".png"):
        mime_type = "image/png"
    elif image_path.lower().endswith(".webp"):
        mime_type = "image/webp"

    base64_image = encode_image(image_path)
    client = _load_groq_client()
    
    system_prompt = """
    You are an expert engineering assistant specialized in reading Piping and Instrumentation Diagrams (P&ID).
    Your task is to analyze the provided image and extract all identifiable components as nodes and their connections as edges.
    
    Infer the types of components (e.g., pump, valve, tank, pipe, sensor) and relationships (e.g., FLOWS_TO, CONTROLS, CONNECTED_TO).
    
    You MUST output valid JSON only. No markdown formatting, no explanation. Just the raw JSON object.
    
    Schema:
    {
      "nodes": [
        {"node_id": "unique_id_1", "entity": "inferred_type", "name": "component_name", "description": "any visible labels or details"}
      ],
      "edges": [
        {"source": "unique_id_1", "target": "unique_id_2", "relation": "INFERRED_RELATION_TYPE"}
      ]
    }
    """

    print("Sending request to Groq Vision LLM...")
    response = client.chat.completions.create(
        model="llama-3.2-11b-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        temperature=0.1,
    )

    output_text = response.choices[0].message.content.strip()
    
    # Strip markdown if present
    if output_text.startswith("```"):
        output_text = output_text.split("\n", 1)[1]
        if output_text.endswith("```"):
            output_text = output_text[:-3]
    output_text = output_text.strip()
    
    try:
        parsed_data = json.loads(output_text)
    except json.JSONDecodeError:
        print("Error: The LLM did not return valid JSON.")
        print("Raw output:", output_text)
        return

    print(f"Extracted {len(parsed_data.get('nodes', []))} nodes and {len(parsed_data.get('edges', []))} edges.")
    
    with open(PID_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2)
        
    print(f"Successfully saved P&ID graph to {PID_GRAPH_PATH}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pid_extractor.py <image_path>")
    else:
        extract_pid_to_graph(sys.argv[1])

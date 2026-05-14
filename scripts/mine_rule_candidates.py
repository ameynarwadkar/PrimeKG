import os
import csv
import json
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import AzureOpenAI
from tqdm import tqdm

# Load environment variables
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# Define paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CYPHER_FILE_PATH = os.path.join(PROJECT_ROOT, "cypher", "rule_mining.cypher")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "outputs", "rule_candidates.csv")

# Fetch query from the cypher file if it exists, else use fallback
if os.path.exists(CYPHER_FILE_PATH):
    with open(CYPHER_FILE_PATH, "r", encoding="utf-8") as f:
        CYPHER_QUERY = f.read()
else:
    CYPHER_QUERY = """
    MATCH (source)-[r1]->(middle)-[r2]->(target)
    WHERE elementId(source) <> elementId(target)
    RETURN
        labels(source) AS source_labels,
        type(r1) AS relation_1,
        labels(middle) AS middle_labels,
        type(r2) AS relation_2,
        labels(target) AS target_labels,
        count(*) AS support
    ORDER BY support DESC
    LIMIT 100;
    """

def get_primary_label(labels):
    """Extract the primary label from a list of labels."""
    filtered = [l for l in labels if l != "Entity"]
    return filtered[0] if filtered else (labels[0] if labels else "")

def verbalize_rule(client, source_label, relation_1, middle_label, relation_2, target_label):
    """Ask Azure OpenAI to verbalize the given graph pattern."""
    prompt = f"""
    You are a biomedical expert. Analyze this frequent 2-hop graph pattern from a knowledge graph:
    Source: {source_label}
    Relation 1: {relation_1}
    Middle: {middle_label}
    Relation 2: {relation_2}
    Target: {target_label}

    Please provide a 'candidate_rule' and a 'possible_use' for this pattern.
    Output ONLY valid JSON in this format:
    {{
        "candidate_rule": "If [Source] [Relation 1] [Middle] and [Middle] [Relation 2] [Target], then [Source] may be candidate for [Target]",
        "possible_use": "short description of use case (e.g., drug repurposing)"
    }}
    Make sure the generated rule sounds natural.
    """
    
    try:
        completion = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You output JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        content = completion.choices[0].message.content
        
        # Safely parse JSON from the response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        data = json.loads(content)
        return data.get("candidate_rule", ""), data.get("possible_use", "")
    except Exception as e:
        print(f"Error verbalizing pattern {source_label}-{relation_1}-{middle_label}-{relation_2}-{target_label}: {e}")
        return "", ""

def main():
    if not NEO4J_PASSWORD:
        raise ValueError("Missing NEO4J_PASSWORD in .env")

    print("Connecting to Neo4j...")
    neo4j_driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    client = None
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT:
        print("Azure OpenAI configured. Will verbalize rules.")
        try:
            client = AzureOpenAI(
                api_key=AZURE_OPENAI_API_KEY,
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_version=AZURE_OPENAI_API_VERSION,
            )
        except Exception as e:
            print(f"Failed to initialize Azure OpenAI client: {e}")
    else:
        print("Azure OpenAI NOT fully configured. Skipping verbalization.")

    print("Running 2-hop pattern query...")
    with neo4j_driver.session() as session:
        result = session.run(CYPHER_QUERY)
        records = list(result)

    print(f"Found {len(records)} patterns.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    csv_columns = [
        "source_labels", "relation_1", "middle_labels", 
        "relation_2", "target_labels", "support", 
        "candidate_rule", "possible_use"
    ]

    print(f"Processing and saving to CSV at {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_columns)

        for record in tqdm(records, desc="Processing patterns"):
            source_labels = record["source_labels"]
            relation_1 = record["relation_1"]
            middle_labels = record["middle_labels"]
            relation_2 = record["relation_2"]
            target_labels = record["target_labels"]
            support = record["support"]

            source_primary = get_primary_label(source_labels)
            middle_primary = get_primary_label(middle_labels)
            target_primary = get_primary_label(target_labels)

            candidate_rule = ""
            possible_use = ""

            if client:
                candidate_rule, possible_use = verbalize_rule(
                    client, source_primary, relation_1, middle_primary, relation_2, target_primary
                )

            writer.writerow([
                source_primary, relation_1, middle_primary, 
                relation_2, target_primary, support, 
                candidate_rule, possible_use
            ])

    neo4j_driver.close()
    print("Done!")

if __name__ == "__main__":
    main()

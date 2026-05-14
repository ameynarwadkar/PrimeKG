import os
import re
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import AzureOpenAI

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

if not NEO4J_PASSWORD:
    raise ValueError("Missing NEO4J_PASSWORD in .env")

if not AZURE_OPENAI_API_KEY:
    raise ValueError("Missing AZURE_OPENAI_API_KEY in .env")

if not AZURE_OPENAI_ENDPOINT:
    raise ValueError("Missing AZURE_OPENAI_ENDPOINT in .env")

if not AZURE_OPENAI_DEPLOYMENT:
    raise ValueError("Missing AZURE_OPENAI_DEPLOYMENT in .env")


neo4j_driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)


GRAPH_SCHEMA = """
You generate Cypher for a Neo4j property graph created from a PrimeKG biomedical subset.

Node labels:

All nodes have label Entity plus a domain label.

1. Disease
   Properties:
   - primekg_index
   - primekg_id
   - name
   - type
   - source

2. Drug
   Properties:
   - primekg_index
   - primekg_id
   - name
   - type
   - source

3. GeneProtein
   Properties:
   - primekg_index
   - primekg_id
   - name
   - type
   - source

4. Phenotype
   Properties:
   - primekg_index
   - primekg_id
   - name
   - type
   - source

5. Pathway
   Properties:
   - primekg_index
   - primekg_id
   - name
   - type
   - source

6. BiologicalProcess
7. MolecularFunction
8. CellularComponent
9. Anatomy
10. Entity

Original PrimeKG relationships:
- Dynamic relationship types from PrimeKG relation column.
- All original relationship properties:
  - relation
  - display_relation
  - source

Derived relationships:

1. (:Drug)-[:CANDIDATE_FOR {
      source: String,
      interpretation: String,
      evidence_gene_count: Integer,
      evidence_genes: List[String],
      drug_gene_relations: List[String],
      gene_disease_relations: List[String]
   }]->(:Disease)

2. (:Disease)-[:INVOLVES_PATHWAY {
      source: String,
      evidence_gene_count: Integer,
      evidence_genes: List[String],
      disease_gene_relations: List[String],
      gene_pathway_relations: List[String]
   }]->(:Pathway)

3. (:Disease)-[:HAS_PHENOTYPE_SIGNAL {
      source: String,
      evidence_count: Integer,
      evidence_relations: List[String]
   }]->(:Phenotype)

4. (:Disease)-[:SHARES_GENE_WITH {
      source: String,
      shared_gene_count: Integer,
      shared_genes: List[String]
   }]->(:Disease)

Important query patterns:

Candidate drugs:
MATCH (drug:Drug)-[r:CANDIDATE_FOR]->(d:Disease)

Disease pathways:
MATCH (d:Disease)-[r:INVOLVES_PATHWAY]->(p:Pathway)

Disease phenotypes:
MATCH (d:Disease)-[r:HAS_PHENOTYPE_SIGNAL]->(p:Phenotype)

Shared genes between diseases:
MATCH (d1:Disease)-[r:SHARES_GENE_WITH]->(d2:Disease)

Evidence path:
MATCH (drug:Drug)-[r1]-(g:GeneProtein)-[r2]-(d:Disease)
"""


SYSTEM_PROMPT = f"""
You translate natural language biomedical questions into Neo4j Cypher.

Use only this graph schema:

{GRAPH_SCHEMA}

Rules:
- Return only Cypher.
- Do not explain.
- Do not wrap in markdown.
- Generate only read-only queries.
- Never use CREATE, MERGE, DELETE, SET, REMOVE, DROP, LOAD CSV, APOC, dbms procedures, or CALL.
- Use MATCH, OPTIONAL MATCH, WITH, WHERE, RETURN, ORDER BY, and LIMIT only.
- Always include LIMIT 20 unless the user asks for counts.
- Use DISTINCT where duplicates are likely.
- Use toLower(x.name) CONTAINS "keyword" for name matching.
- NEVER use toString() on List/Array properties. To search inside a List[String], use the ANY() function: ANY(item IN x.list_property WHERE toLower(item) CONTAINS "keyword").
- For candidate drug questions, prefer the derived CANDIDATE_FOR relationship.
- For pathway questions, prefer INVOLVES_PATHWAY.
- For phenotype/symptom questions, prefer HAS_PHENOTYPE_SIGNAL.
- For similar disease questions, prefer SHARES_GENE_WITH.
- For "why" or "explain" questions, return rule source, evidence genes, relation types, and evidence counts.
- Do not make medical claims. Return graph-derived candidates/evidence only.
"""


FORBIDDEN_PATTERNS = [
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bLOAD\s+CSV\b",
    r"\bCALL\b",
    r"\bAPOC\b",
    r"\bDBMS\b",
    r"\bDETACH\b",
]


def clean_cypher(cypher: str) -> str:
    cypher = cypher.strip()
    cypher = cypher.replace("```cypher", "")
    cypher = cypher.replace("```", "")
    return cypher.strip()


def validate_cypher(cypher: str) -> bool:
    upper = cypher.upper()

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, upper):
            raise ValueError(f"Unsafe Cypher blocked. Forbidden pattern: {pattern}")

    allowed_start = (
        "MATCH",
        "OPTIONAL MATCH",
        "WITH",
    )

    if not upper.startswith(allowed_start):
        raise ValueError(
            "Unsafe Cypher blocked. Query must start with MATCH, OPTIONAL MATCH, or WITH."
        )

    if not re.search(r"\bRETURN\b", upper):
        raise ValueError("Invalid Cypher blocked. Query must contain RETURN.")

    return True


def generate_cypher(question: str) -> str:
    completion = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )

    cypher = completion.choices[0].message.content
    cypher = clean_cypher(cypher)
    validate_cypher(cypher)

    return cypher


def run_cypher(cypher: str):
    with neo4j_driver.session() as session:
        result = session.run(cypher)
        return [record.data() for record in result]


def print_rows(rows):
    if not rows:
        print("\nNo results found.")
        return

    print("\nRaw Results:")
    for i, row in enumerate(rows, start=1):
        print(f"\n[{i}]")
        for key, value in row.items():
            print(f"{key}: {value}")


def format_answer_with_llm(question: str, cypher: str, rows: list) -> str:
    prompt = f"""
You are a biomedical expert interpreting results from a knowledge graph query.
The user asked: "{question}"
The Cypher query generated was:
{cypher}
The raw JSON results returned by the graph database are (limited to first 5):
{rows[:5]}

Please format the response strictly following this structure:

Question:
[The original question]

Answer:
[A clear natural language summary of the findings based on the provided rows]

Evidence path:
[Show the graph path using arrows, e.g. Drug X --TARGETS--> Gene G --ASSOCIATED_WITH--> Disease Y. If multiple paths exist, summarize or list a few clear examples.]

Rule used:
[Explain the logical rule if a derived relationship or multi-hop path was used, e.g. Drug TARGETS Gene + Gene ASSOCIATED_WITH Disease -> Drug CANDIDATE_FOR Disease. If it's a simple lookup, just state the direct relation used.]
"""

    completion = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "You output plain text strictly in the requested format."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return completion.choices[0].message.content.strip()


def main():
    print("\nPrimeKG Neo4j Biomedical QA using Azure OpenAI")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("Ask > ").strip()

        if question.lower() in {"exit", "quit"}:
            break

        if not question:
            continue

        try:
            cypher = generate_cypher(question)

            print("\nGenerated Cypher:")
            print(cypher)

            rows = run_cypher(cypher)
            
            if not rows:
                print("\nNo results found.")
            else:
                print("\n" + "="*50)
                formatted_response = format_answer_with_llm(question, cypher, rows)
                print(formatted_response)
                print("="*50)

        except Exception as e:
            print("\nError:")
            print(e)

    neo4j_driver.close()


if __name__ == "__main__":
    main()
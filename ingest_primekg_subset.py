import os
import re
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "primekg")
INPUT_PATH = "outputs/primekg_alzheimer_subset.csv"
CHUNK_SIZE = 1000

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


TYPE_TO_LABEL = {
    "disease": "Disease",
    "drug": "Drug",
    "gene/protein": "GeneProtein",
    "effect/phenotype": "Phenotype",
    "biological_process": "BiologicalProcess",
    "molecular_function": "MolecularFunction",
    "cellular_component": "CellularComponent",
    "pathway": "Pathway",
    "anatomy": "Anatomy",
}


def safe_rel_type(value):
    value = str(value or "RELATED_TO").strip()
    value = re.sub(r"[^A-Za-z0-9_]", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    value = value.upper()

    if not value:
        value = "RELATED_TO"

    if value[0].isdigit():
        value = "REL_" + value

    return value


def label_for(node_type):
    node_type = str(node_type or "").strip()
    return TYPE_TO_LABEL.get(node_type, "Entity")


def create_constraints(tx):
    tx.run("""
    CREATE CONSTRAINT entity_index IF NOT EXISTS
    FOR (e:Entity)
    REQUIRE e.primekg_index IS UNIQUE
    """)


def ingest_row(tx, row):
    x_label = label_for(row["x_type"])
    y_label = label_for(row["y_type"])
    rel_type = safe_rel_type(row["relation"])

    query = f"""
    MERGE (x:Entity:{x_label} {{primekg_index: $x_index}})
    SET x.primekg_id = $x_id,
        x.name = $x_name,
        x.type = $x_type,
        x.source = $x_source

    MERGE (y:Entity:{y_label} {{primekg_index: $y_index}})
    SET y.primekg_id = $y_id,
        y.name = $y_name,
        y.type = $y_type,
        y.source = $y_source

    MERGE (x)-[r:{rel_type} {{relation: $relation}}]->(y)
    SET r.display_relation = $display_relation,
        r.source = "PrimeKG"
    """

    tx.run(query, {
        "x_index": str(row.get("x_index", "")),
        "x_id": str(row.get("x_id", "")),
        "x_type": str(row.get("x_type", "")),
        "x_name": str(row.get("x_name", "")),
        "x_source": str(row.get("x_source", "")),
        "y_index": str(row.get("y_index", "")),
        "y_id": str(row.get("y_id", "")),
        "y_type": str(row.get("y_type", "")),
        "y_name": str(row.get("y_name", "")),
        "y_source": str(row.get("y_source", "")),
        "relation": str(row.get("relation", "")),
        "display_relation": str(row.get("display_relation", "")),
    })


def main():
    if not NEO4J_PASSWORD:
        raise ValueError("Missing NEO4J_PASSWORD in .env")

    print("Creating constraints...")

    with driver.session() as session:
        session.execute_write(create_constraints)

    print(f"Ingesting: {INPUT_PATH}")

    df = pd.read_csv(INPUT_PATH, low_memory=False).fillna("")
    print(f"Rows to ingest: {len(df)}")

    with driver.session() as session:
        for _, row in tqdm(df.iterrows(), total=len(df)):
            session.execute_write(ingest_row, row)

    driver.close()
    print("PrimeKG subset ingestion complete.")


if __name__ == "__main__":
    main()
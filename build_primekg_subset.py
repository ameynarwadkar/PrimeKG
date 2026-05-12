import pandas as pd
from tqdm import tqdm

KG_PATH = "data/kg.csv"
OUTPUT_PATH = "outputs/primekg_alzheimer_subset.csv"

KEYWORD = "alzheimer"
CHUNK_SIZE = 100_000
MAX_ROWS = 100_000

ALLOWED_TYPES = {
    "disease",
    "drug",
    "gene/protein",
    "effect/phenotype",
    "biological_process",
    "molecular_function",
    "cellular_component",
    "pathway",
    "anatomy",
}


def normalize_str(series):
    return series.astype(str).str.lower()


def main():
    print(f"Building PrimeKG subset around keyword: {KEYWORD}")

    first_hop_nodes = set()
    direct_rows = []

    print("\nPass 1: finding disease-centered first-hop neighborhood...")

    for chunk in tqdm(pd.read_csv(KG_PATH, chunksize=CHUNK_SIZE, low_memory=False)):
        chunk = chunk.fillna("")

        x_match = normalize_str(chunk["x_name"]).str.contains(KEYWORD, na=False)
        y_match = normalize_str(chunk["y_name"]).str.contains(KEYWORD, na=False)

        matched = chunk[x_match | y_match].copy()

        if len(matched) > 0:
            first_hop_nodes.update(matched["x_index"].astype(str).tolist())
            first_hop_nodes.update(matched["y_index"].astype(str).tolist())
            direct_rows.append(matched)

    print(f"First-hop nodes collected: {len(first_hop_nodes)}")

    if not first_hop_nodes:
        raise ValueError("No matching nodes found. Try another keyword, e.g. diabetes, cancer, autism.")

    selected_rows = []

    if direct_rows:
        selected_rows.extend(direct_rows)

    print("\nPass 2: collecting useful one-hop/two-hop biomedical context...")

    total_selected = sum(len(df) for df in selected_rows)

    for chunk in tqdm(pd.read_csv(KG_PATH, chunksize=CHUNK_SIZE, low_memory=False)):
        chunk = chunk.fillna("")

        x_in = chunk["x_index"].astype(str).isin(first_hop_nodes)
        y_in = chunk["y_index"].astype(str).isin(first_hop_nodes)

        x_type_allowed = chunk["x_type"].astype(str).isin(ALLOWED_TYPES)
        y_type_allowed = chunk["y_type"].astype(str).isin(ALLOWED_TYPES)

        # Avoid exploding protein-protein edges in the first prototype
        both_protein = (
            (chunk["x_type"].astype(str) == "gene/protein")
            & (chunk["y_type"].astype(str) == "gene/protein")
        )

        selected = chunk[(x_in | y_in) & x_type_allowed & y_type_allowed & ~both_protein].copy()

        if len(selected) > 0:
            selected_rows.append(selected)
            total_selected += len(selected)

        if total_selected >= MAX_ROWS:
            break

    subset = pd.concat(selected_rows, ignore_index=True)
    subset = subset.drop_duplicates()

    if len(subset) > MAX_ROWS:
        subset = subset.head(MAX_ROWS)

    subset.to_csv(OUTPUT_PATH, index=False)

    print(f"\nSaved subset: {OUTPUT_PATH}")
    print(f"Rows: {len(subset)}")

    print("\nNode types:")
    print(pd.concat([subset["x_type"], subset["y_type"]]).value_counts())

    print("\nRelations:")
    print(subset["relation"].value_counts().head(50))


if __name__ == "__main__":
    main()
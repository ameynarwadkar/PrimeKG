import pandas as pd

KG_PATH = "data/kg.csv"

def main():
    df = pd.read_csv(KG_PATH, nrows=500, low_memory=False)

    print("\nColumns:")
    print(df.columns.tolist())

    print("\nFirst rows:")
    print(df.head())

    print("\nNode types from x_type:")
    print(df["x_type"].value_counts().head(30))

    print("\nNode types from y_type:")
    print(df["y_type"].value_counts().head(30))

    print("\nRelations:")
    print(df["relation"].value_counts().head(50))

    print("\nDisplay relations:")
    print(df["display_relation"].value_counts().head(50))

    print("\nDisease names containing Alzheimer:")
    mask_x = df["x_name"].astype(str).str.lower().str.contains("alzheimer", na=False)
    mask_y = df["y_name"].astype(str).str.lower().str.contains("alzheimer", na=False)
    print(df[mask_x | mask_y][["x_index", "x_type", "x_name", "relation", "y_index", "y_type", "y_name"]].head(30))

if __name__ == "__main__":
    main()
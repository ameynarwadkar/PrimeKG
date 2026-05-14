import os
import sys
import pandas as pd
from tqdm import tqdm

# Add project root to sys.path to import the QA logic
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

from nl_to_cypher_primekg import generate_cypher, run_cypher

QUESTIONS_FILE = os.path.join(PROJECT_ROOT, "questions", "primekg_qa_questions.csv")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "outputs", "qa_eval_results.csv")

DERIVED_RULES = ["CANDIDATE_FOR", "INVOLVES_PATHWAY", "HAS_PHENOTYPE_SIGNAL", "SHARES_GENE_WITH"]

def check_used_derived_rule(cypher: str) -> bool:
    """Check if the Cypher query utilizes our derived rules."""
    upper_cypher = cypher.upper()
    return any(rule in upper_cypher for rule in DERIVED_RULES)

def check_has_evidence_path(cypher: str) -> bool:
    """Check if the Cypher query extracts evidence or paths."""
    upper_cypher = cypher.upper()
    keywords = ["EVIDENCE", "SOURCE", "RELATIONS", "PATH"]
    has_keywords = any(kw in upper_cypher for kw in keywords)
    # Check for multi-hop graph patterns (e.g. ()-[]-()-[]-())
    has_multi_hop = upper_cypher.count(")-[") > 1 or upper_cypher.count("]-(") > 1
    return has_keywords or has_multi_hop

def main():
    if not os.path.exists(QUESTIONS_FILE):
        print(f"Questions file not found: {QUESTIONS_FILE}")
        return

    print("Loading evaluation questions...")
    df = pd.read_csv(QUESTIONS_FILE)
    
    results = []
    
    print(f"Evaluating QA system on {len(df)} questions...")
    
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Evaluating"):
        q_id = row.get("id", "")
        question = row.get("question", "")
        
        generated_cypher = ""
        execution_success = False
        number_of_rows = 0
        used_derived_rule = False
        has_evidence_path = False
        error_message = ""
        
        try:
            # 1. Generate Cypher
            generated_cypher = generate_cypher(question)
            
            # 2. Extract metrics
            used_derived_rule = check_used_derived_rule(generated_cypher)
            has_evidence_path = check_has_evidence_path(generated_cypher)
            
            # 3. Execute Cypher against Neo4j
            rows = run_cypher(generated_cypher)
            execution_success = True
            number_of_rows = len(rows)
            
        except Exception as e:
            execution_success = False
            error_message = str(e).strip()
            
        results.append({
            "id": q_id,
            "question": question,
            "generated_cypher": generated_cypher,
            "execution_success": execution_success,
            "number_of_rows": number_of_rows,
            "used_derived_rule": used_derived_rule,
            "has_evidence_path": has_evidence_path,
            "error_message": error_message
        })
        
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Save detailed evaluation log
    eval_df = pd.DataFrame(results)
    eval_df.to_csv(OUTPUT_FILE, index=False)
    
    print(f"\nEvaluation complete. Detailed log saved to {OUTPUT_FILE}")
    
    # Calculate and print summary metrics
    if len(eval_df) > 0:
        success_rate = eval_df["execution_success"].mean() * 100
        avg_rows = eval_df[eval_df["execution_success"]]["number_of_rows"].mean() if eval_df["execution_success"].any() else 0
        rule_usage = eval_df["used_derived_rule"].mean() * 100
        evidence_usage = eval_df["has_evidence_path"].mean() * 100
        
        print("\n--- Evaluation Summary ---")
        print(f"Total Questions Evaluated: {len(eval_df)}")
        print(f"Execution Success Rate: {success_rate:.1f}%")
        print(f"Avg Rows Returned (Successful): {avg_rows:.1f}")
        print(f"Used Derived Rule: {rule_usage:.1f}%")
        print(f"Has Evidence Path: {evidence_usage:.1f}%")

if __name__ == "__main__":
    main()

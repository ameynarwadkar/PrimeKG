// =====================================================
// PrimeKG Biomedical Rule Derivation
// Safer version with evidence counts
// =====================================================


// -----------------------------------------------------
// Cleanup old derived relations
// -----------------------------------------------------

MATCH ()-[r:CANDIDATE_FOR]->()
DELETE r;

MATCH ()-[r:INVOLVES_PATHWAY]->()
DELETE r;

MATCH ()-[r:HAS_PHENOTYPE_SIGNAL]->()
DELETE r;

MATCH ()-[r:SHARES_GENE_WITH]->()
DELETE r;


// -----------------------------------------------------
// RULE 1:
// Drug-Gene-Disease candidate rule
//
// IF Drug is connected to GeneProtein
// AND GeneProtein is connected to Disease
// THEN Drug is a candidate hypothesis for Disease
//
// Important: this does NOT mean the drug treats the disease.
// It means there is an evidence path worth inspecting.
// -----------------------------------------------------

MATCH (drug:Drug)-[r1]-(g:GeneProtein)-[r2]-(d:Disease)
WHERE toLower(d.name) CONTAINS "alzheimer"
WITH
    drug,
    d,
    count(DISTINCT g) AS evidence_gene_count,
    collect(DISTINCT g.name)[0..10] AS evidence_genes,
    collect(DISTINCT r1.display_relation)[0..5] AS drug_gene_relations,
    collect(DISTINCT r2.display_relation)[0..5] AS gene_disease_relations
WHERE evidence_gene_count >= 1
MERGE (drug)-[r:CANDIDATE_FOR]->(d)
SET
    r.source = "rule_drug_gene_disease_path",
    r.interpretation = "candidate hypothesis, not confirmed treatment",
    r.evidence_gene_count = evidence_gene_count,
    r.evidence_genes = evidence_genes,
    r.drug_gene_relations = drug_gene_relations,
    r.gene_disease_relations = gene_disease_relations;


// -----------------------------------------------------
// RULE 2:
// Disease-Gene-Pathway rule
//
// IF Disease is connected to GeneProtein
// AND GeneProtein is connected to Pathway
// THEN Disease may involve Pathway
// -----------------------------------------------------

MATCH (d:Disease)-[r1]-(g:GeneProtein)-[r2]-(p:Pathway)
WHERE toLower(d.name) CONTAINS "alzheimer"
WITH
    d,
    p,
    count(DISTINCT g) AS evidence_gene_count,
    collect(DISTINCT g.name)[0..10] AS evidence_genes,
    collect(DISTINCT r1.display_relation)[0..5] AS disease_gene_relations,
    collect(DISTINCT r2.display_relation)[0..5] AS gene_pathway_relations
WHERE evidence_gene_count >= 1
MERGE (d)-[r:INVOLVES_PATHWAY]->(p)
SET
    r.source = "rule_disease_gene_pathway",
    r.evidence_gene_count = evidence_gene_count,
    r.evidence_genes = evidence_genes,
    r.disease_gene_relations = disease_gene_relations,
    r.gene_pathway_relations = gene_pathway_relations;


// -----------------------------------------------------
// RULE 3:
// Disease-Phenotype signal rule
//
// IF Disease is connected to Phenotype
// THEN Disease has phenotype signal
// -----------------------------------------------------

MATCH (d:Disease)-[r1]-(p:Phenotype)
WHERE toLower(d.name) CONTAINS "alzheimer"
WITH
    d,
    p,
    count(r1) AS evidence_count,
    collect(DISTINCT r1.display_relation)[0..5] AS evidence_relations
MERGE (d)-[r:HAS_PHENOTYPE_SIGNAL]->(p)
SET
    r.source = "rule_disease_phenotype_connection",
    r.evidence_count = evidence_count,
    r.evidence_relations = evidence_relations;


// -----------------------------------------------------
// RULE 4:
// Disease-Disease shared gene rule
//
// IF Disease D1 is connected to Gene G
// AND Disease D2 is connected to same Gene G
// THEN D1 shares genetic evidence with D2
// -----------------------------------------------------

MATCH (d1:Disease)-[r1]-(g:GeneProtein)-[r2]-(d2:Disease)
WHERE d1.primekg_index < d2.primekg_index
  AND (
      toLower(d1.name) CONTAINS "alzheimer"
      OR toLower(d2.name) CONTAINS "alzheimer"
  )
WITH
    d1,
    d2,
    count(DISTINCT g) AS shared_gene_count,
    collect(DISTINCT g.name)[0..10] AS shared_genes
WHERE shared_gene_count >= 2
MERGE (d1)-[r:SHARES_GENE_WITH]->(d2)
SET
    r.source = "rule_diseases_share_genes",
    r.shared_gene_count = shared_gene_count,
    r.shared_genes = shared_genes;


// -----------------------------------------------------
// Check derived relation counts
// -----------------------------------------------------

MATCH ()-[r]->()
WHERE type(r) IN [
    "CANDIDATE_FOR",
    "INVOLVES_PATHWAY",
    "HAS_PHENOTYPE_SIGNAL",
    "SHARES_GENE_WITH"
]
RETURN type(r) AS derived_relation,
       count(r) AS count
ORDER BY count DESC;
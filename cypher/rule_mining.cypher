// Frequent 2-hop typed graph patterns

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
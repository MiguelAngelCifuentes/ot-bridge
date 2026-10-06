-- V2: los operadores se almacenan en mayusculas (enum Java @Enumerated(STRING));
-- el seed inicial de V1 los inserto en minusculas.
UPDATE thresholds SET operator = UPPER(operator);

-- add new 'word' column to kbest, use that for access

ALTER TABLE kbest ADD COLUMN word VARCHAR(255) BEFORE doc_id;

UPDATE kbest k SET word = (SELECT original FROM token t WHERE t.doc_id = k.doc_id AND t.doc_index = k.doc_index);

ALTER TABLE kbest MODIFY COLUMN word VARCHAR(255) NOT NULL;

CREATE INDEX idx_kbest_word
    ON kbest(word);

CREATE INDEX idx_kbest_word_k
    ON kbest(word, k);

-- remove old columns

DROP INDEX idx_kbest_doc_id_doc_index;
DROP INDEX idx_kbest_doc_id_doc_index_k;

ALTER TABLE DROP COLUMN doc_id;
ALTER TABLE DROP COLUMN doc_index;
CREATE TABLE token (
	doc_id VARCHAR(255) NOT NULL,
	doc_index INT NOT NULL,
	original VARCHAR(255) NOT NULL,
	hyphenated BOOLEAN,
	discarded BOOLEAN,
	gold VARCHAR(255),
	bin INT,
	heuristic VARCHAR(1),
	decision VARCHAR(255),
	selection VARCHAR(255),
	token_type VARCHAR(255),
	token_info TEXT,
	annotations TEXT,
	has_error BOOLEAN,
	last_modified TIMESTAMP,
	PRIMARY KEY (doc_id, doc_index)
);

CREATE TABLE kbest (
	word VARCHAR(255) NOT NULL,
	k INT NOT NULL,
	candidate VARCHAR(255) NOT NULL,
	probability float NOT NULL,
	PRIMARY KEY (word, k)
);

CREATE INDEX idx_token_doc_id_doc_index
	ON token(doc_id, doc_index);

CREATE INDEX idx_kbest_word
    ON kbest(word);

CREATE INDEX idx_kbest_word_k
    ON kbest(word, k);

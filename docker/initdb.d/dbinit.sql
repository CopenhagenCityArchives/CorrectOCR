CREATE TABLE documents (
	doc_id VARCHAR(255) PRIMARY KEY,
	ext VARCHAR(10) NOT NULL,
	original_path VARCHAR(255) NOT NULL,
	gold_path VARCHAR(255) NOT NULL,
	is_done BOOLEAN
);

CREATE INDEX idx_docs
	ON documents(doc_id);

CREATE TABLE token (
	doc_id VARCHAR(255) NOT NULL,
	doc_index INT NOT NULL,
	original VARCHAR(255) NOT NULL,
	hyphenated BOOLEAN,
	discarded BOOLEAN,
	gold VARCHAR(255),
	bin INT,
	heuristic VARCHAR(15),
	selection VARCHAR(255),
	token_type VARCHAR(255),
	token_info TEXT,
	annotations TEXT,
	has_error BOOLEAN,
	last_modified TIMESTAMP,
	PRIMARY KEY (doc_id, doc_index)
);

CREATE TABLE kbest (
	doc_id VARCHAR(255) NOT NULL,
	doc_index INT NOT NULL,
	k INT NOT NULL,
	candidate VARCHAR(255) NOT NULL,
	probability float NOT NULL,
	PRIMARY KEY (doc_id, doc_index, k)
);

CREATE INDEX idx_token_doc_id_doc_index
	ON token(doc_id, doc_index);

CREATE INDEX idx_kbest_doc_id_doc_index
	ON kbest(doc_id, doc_index);

CREATE INDEX idx_kbest_doc_id_doc_index_k
    ON kbest(doc_id, doc_index, k);

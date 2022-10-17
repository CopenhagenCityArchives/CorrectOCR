CREATE TABLE documents (
	id INT NOT NULL,
	doc_id VARCHAR(255) NOT NULL,
	ext VARCHAR(10) NOT NULL,
	original_path VARCHAR(255) NOT NULL,
	gold_path VARCHAR(255) NOT NULL,
	is_done BOOLEAN,
	PRIMARY KEY (id)
);

CREATE INDEX idx_docs
	ON documents(doc_id);

CREATE TABLE token (
	id INT NOT NULL,
	doc_id INT NOT NULL,
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
	PRIMARY KEY (id),
	FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE TABLE kbest (
	token_id INT NOT NULL,
	k INT NOT NULL,
	candidate VARCHAR(255) NOT NULL,
	probability float NOT NULL,
	PRIMARY KEY (token_id, k),
	FOREIGN KEY (token_id) REFERENCES token(id)
);


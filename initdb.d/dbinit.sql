CREATE TABLE token (
	id INT NOT NULL AUTO_INCREMENT,
	original VARCHAR(255) NOT NULL,
	gold VARCHAR(255),
	bin INT,
	heuristic VARCHAR(1),
	decision VARCHAR(255),
	selection VARCHAR(255),
	token_type VARCHAR(255),
	token_info TEXT,
	file_id VARCHAR(255) NOT NULL,
	file_index INT NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE kbest (
	id INT NOT NULL AUTO_INCREMENT,
	token_id INT NOT NULL,
	k INT NOT NULL,
	candidate VARCHAR(255) NOT NULL,
	probability float NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT FOREIGN KEY fk_kbest_token (token_id) REFERENCES token(id)
);
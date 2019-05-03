Gold varchar(255)
Original varchar(255)
Bin int
Heuristic varchar(1)
Decision varchar(255)
Selection varchar(255)
Token type varchar(255)
Token info text
File ID varchar(255)
Index int


CREATE TABLE Token
	id primary key
	;

CREATE TABLE KBestItem
	id primary key not null 
	token foreignkey,
	k int,
	candidate varchar(255),
	probability float
	;
FROM python:3.7

RUN apt update && apt install -y tesseract-ocr libtesseract-dev libleptonica-dev mupdf unixodbc-dev wait-for-it
RUN curl -SL https://dev.mysql.com/get/Downloads/Connector-ODBC/8.0/mysql-connector-odbc-8.0.19-linux-debian10-x86-64bit.tar.gz | tar -zxC /opt
RUN cp /opt/mysql-connector-odbc-8.0.19-linux-debian10-x86-64bit/lib/libmyodbc8* /usr/lib/x86_64-linux-gnu/odbc/
RUN /opt/mysql-connector-odbc-8.0.19-linux-debian10-x86-64bit/bin/myodbc-installer -d -a -n "MySQL ODBC 8.0 ANSI Driver" -t "DRIVER=/usr/lib/x86_64-linux-gnu/odbc/libmyodbc8a.so;"
RUN /opt/mysql-connector-odbc-8.0.19-linux-debian10-x86-64bit/bin/myodbc-installer -d -a -n "MySQL ODBC 8.0 Unicode Driver" -t "DRIVER=/usr/lib/x86_64-linux-gnu/odbc/libmyodbc8w.so;"

WORKDIR /app

# Install requirements
COPY ./requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Copy code and its config
COPY ./CorrectOCR ./CorrectOCR
COPY ./CorrectOCR.ini ./
COPY ./uwsgi.py ./

EXPOSE 5000

ENTRYPOINT uwsgi --socket /tmp/correctocr.sock --http :5000 --wsgi-file uwsgi.py --callable app --processes 20 --threads 8 --http-timeout 300 --uid nobody --gid nogroup --master
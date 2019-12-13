FROM python:3.7

RUN apt update
RUN apt install -y tesseract-ocr libtesseract-dev libleptonica-dev mupdf unixodbc-dev

COPY ./requirements.txt /requirements.txt
RUN pip3 install -r requirements.txt
COPY ./CorrectOCR /CorrectOCR
EXPOSE 5000

ENTRYPOINT [ "python3", "-m", "CorrectOCR", "server", "--host", "0.0.0.0" ]
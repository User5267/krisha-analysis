FROM python:3.12-slim

WORKDIR /app

COPY wheels/ /wheels/
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY krisha_parser.py .

RUN mkdir -p /data

ENTRYPOINT ["python", "krisha_parser.py"]
CMD ["--output-dir", "/data", "--max-pages", "50", "--delay", "2.0"]
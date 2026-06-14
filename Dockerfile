FROM python:3.14-slim-bookworm

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

CMD ["python3","main.py"]

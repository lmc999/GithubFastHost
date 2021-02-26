FROM python:3

WORKDIR /usr/src/app

RUN pip install --no-cache-dir aiohttp

COPY gh-check.py .

CMD ["python", "./gh-check.py"]

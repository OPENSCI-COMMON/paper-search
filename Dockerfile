FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for lxml and other native packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY paper_search/ paper_search/

RUN pip install --no-cache-dir ".[mcp]"

EXPOSE 8000

ENTRYPOINT ["paper-search-mcp"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]

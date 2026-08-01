FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app \
    PIP_ROOT_USER_ACTION=ignore

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy source and data
COPY . .

# Create data directory
RUN mkdir -p data

# Expose Streamlit port
EXPOSE 8501

# Entrypoint: run ingestion then launch Streamlit
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

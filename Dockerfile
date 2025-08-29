# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# Evita buffer no log
ENV PYTHONUNBUFFERED=1

# Pasta de trabalho
WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY main.py .

# A imagem do Playwright já vem com os browsers instalados.
# Exposição e comando (Render define $PORT)
CMD ["bash", "-lc", "uvicorn main:app --host 0.0.0.0 --port $PORT"]

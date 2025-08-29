# Imagem oficial do Playwright com Python + browsers (Jammy)
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# Evita que a imagem tente buscar browsers fora
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Porta que o Render expõe automaticamente
ENV PORT=8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# imagem oficial do Playwright + Python
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# evita prompts interativos
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# diretório da app
WORKDIR /app

# copiar dependências
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copiar código
COPY main.py /app/main.py

# (opcional) baixar os browsers; a imagem já vem, mas garantimos:
RUN playwright install --with-deps chromium

# porta padrão do Render
ENV PORT=10000

# iniciar a API
# uvicorn escuta em 0.0.0.0 e usa a variável de PORT que o Render injeta
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]

# Imagem oficial com Python + Playwright + navegadores
FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app

# Copia e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY . .

# Porta do app
ENV PORT=10000
EXPOSE 10000

# Sobe a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

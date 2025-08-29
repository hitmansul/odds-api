# Imagem base estável Debian (boa compatibilidade no Render)
FROM python:3.11-bookworm

# Cria pasta de trabalho
WORKDIR /app

# (Opcional) garante menos logs interativos
ENV PYTHONUNBUFFERED=1
# Onde os navegadores do Playwright ficam (cache de camadas Docker)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Atualiza pip e instala dependências Python do projeto
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Instala o Chromium + dependências do sistema de uma vez
RUN python -m playwright install --with-deps chromium

# Copia o restante do código
COPY . .

# Porta que o Render utiliza por padrão
EXPOSE 10000

# Se seu app for FastAPI/Starlette:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

# --- Se for Streamlit, comente a linha acima e use esta: ---
# CMD ["streamlit", "run", "app.py", "--server.port=10000", "--server.address=0.0.0.0"]

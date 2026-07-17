# ==========================================
# Estágio 1: Build
# ==========================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Caso alguma biblioteca futura precise de compiladores (como gcc), 
# você pode instalar aqui. Para o requirements atual, mantemos limpo.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instala as dependências no diretório do usuário (~/.local) e remove o cache do pip
RUN pip install --no-cache-dir --user -r requirements.txt

# ==========================================
# Estágio 2: Final
# ==========================================
FROM python:3.13-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Garante que o Python encontre os executáveis e pacotes copiados no PATH
    PATH=/root/.local/bin:$PATH

WORKDIR /app

# Copia apenas as dependências instaladas e limpas do estágio anterior
COPY --from=builder /root/.local /root/.local

# Copia o código-fonte da aplicação
COPY app.py .

# Mantida a porta original do seu arquivo
EXPOSE 8003

CMD ["gunicorn", "--bind", "0.0.0.0:8003", "--workers", "4", "app:app"]
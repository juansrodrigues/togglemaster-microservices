# ==========================================
# Estágio 1: Build
# ==========================================
FROM python:3.13-slim AS builder

WORKDIR /app

# Entender melhor esse RUN
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instala as dependências no diretório do usuário (__USER_BASE__)
RUN pip install --no-cache-dir --user -r requirements.txt

# ==========================================
# Estágio 2: Execução
# ==========================================
FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Garante que o Python encontre os pacotes copiados no PATH do usuário
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# Copia apenas as dependências instaladas do estágio anterior
COPY --from=builder /root/.local /root/.local

# Copia o código da aplicação
COPY app.py .

EXPOSE 8005

ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:8005", "--workers", "4", "app:app"]

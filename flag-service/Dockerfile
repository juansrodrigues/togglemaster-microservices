# ==========================================
# Estágio 1: Build
# ==========================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Instala ferramentas necessárias para compilar dependências Python (ex: pacotes C)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .

# Instala as dependências no diretório de usuário (~/.local) sem salvar cache local
RUN pip install --no-cache-dir --user -r requirements.txt

# ==========================================
# Estágio 2: Final
# ==========================================
FROM python:3.13-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Garante que o Python encontre os binários e pacotes copiados no PATH do usuário
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# O Alpine/Debian precisa da biblioteca de runtime do Postgres para o driver funcionar
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copia apenas as dependências prontas do estágio de build
COPY --from=builder /root/.local /root/.local

# Copia o restante do código-fonte da aplicação
COPY . .

EXPOSE 8002

CMD ["python", "app.py"]
# ToggleMaster — Feature Flag Management System

Sistema de **feature flags** decomposto em 5 microsserviços independentes, containerizados com Docker e orquestrados no **Azure Kubernetes Service (AKS)**.

Desenvolvido como Tech Challenge Fase 2 — POSTECH/FIAP DevOps & Cloud Architecture.

---

## O que é uma feature flag?

Uma feature flag é um "interruptor" no código que permite ativar ou desativar funcionalidades sem precisar de um novo deploy. Em vez de lançar uma feature para todos os usuários de uma vez, você controla quem vê o quê — por exemplo, ativando para 10% dos usuários primeiro e expandindo gradualmente.

---

## Arquitetura

```
Cliente / Postman
       │
       ▼
Application Gateway (Azure) + AGIC
       │ roteia por path
       ▼
┌──────────────────────── AKS — namespace: toggle-apps ────────────────────────┐
│                                                                               │
│  /admin, /validate  →  auth-service (Go)         →  PostgreSQL (auth_db)     │
│  /flags             →  flag-service (Python)      →  PostgreSQL (flags_db)    │
│  /rules             →  targeting-service (Python)  →  PostgreSQL (targeting_db)│
│  /evaluate          →  evaluation-service (Go)    →  Redis (cache, TTL 30s)  │
│                                          │         →  Service Bus (evento)    │
│                                          ▼                                    │
│                         analytics-service (Python) ←  Service Bus             │
│                                          │         →  Cosmos DB               │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Os 5 microsserviços

### auth-service · Go · porta 8001

Responsável pela criação e validação de chaves de API.

- Gera chaves aleatórias de 256 bits com prefixo `tm_key_`
- **Nunca armazena a chave em texto plano** — só o hash SHA-256
- A cada requisição dos outros serviços, valida a chave recalculando o hash e comparando com o banco
- Construído em Go, dividido em três arquivos:
  - `main.go` — inicializa o servidor, rotas e conexão com PostgreSQL
  - `handlers.go` — lógica dos endpoints (`/health`, `/validate`, `/admin/keys`)
  - `key.go` — geração de chaves aleatórias e hashing SHA-256

**Endpoints:**

| Método | Path | Autenticação | Função |
|---|---|---|---|
| GET | `/health` | Nenhuma | Health check (usado pelo Kubernetes) |
| GET | `/validate` | Bearer token | Valida uma API key |
| POST | `/admin/keys` | MASTER_KEY | Cria nova API key |

**Banco de dados:** PostgreSQL (`auth_db`) — tabela `api_keys`

---

### flag-service · Python/Flask · porta 8002

CRUD completo das definições de feature flags.

- Cada flag tem `name` (identificador único), `description` e `is_enabled`
- `is_enabled: false` é o kill switch global — desativa a flag para todos os usuários imediatamente
- Toda requisição valida a API key chamando o auth-service antes de executar qualquer operação
- Usa `psycopg2` para conexão com PostgreSQL e `gunicorn` como servidor de produção

**Endpoints (todos requerem Bearer token):**

| Método | Path | Função |
|---|---|---|
| POST | `/flags` | Cria flag |
| GET | `/flags` | Lista todas |
| GET | `/flags/{name}` | Busca uma específica |
| PUT | `/flags/{name}` | Atualiza |
| DELETE | `/flags/{name}` | Remove |

**Banco de dados:** PostgreSQL (`flags_db`) — tabela `flags`

---

### targeting-service · Python/Flask · porta 8003

Gerencia regras de segmentação — define quem vê cada flag.

- Cada flag pode ter uma regra associada
- Regra suportada: `PERCENTAGE` — ativa a flag para X% dos usuários
- A regra é armazenada como `JSONB` no PostgreSQL, permitindo adicionar novos tipos no futuro sem alterar o schema
- Mesma autenticação via auth-service que o flag-service

**Exemplo de regra:**
```json
{
    "flag_name": "enable-new-dashboard",
    "is_enabled": true,
    "rules": {
        "type": "PERCENTAGE",
        "value": 50
    }
}
```

**Banco de dados:** PostgreSQL (`targeting_db`) — tabela `targeting_rules` com campo `rules JSONB`

---

### evaluation-service · Go · porta 8004

O hot path do sistema — retorna `true` ou `false` para cada combinação de usuário + flag.

**Fluxo de uma requisição:**

```
GET /evaluate?user_id=user-123&flag_name=demo

1. Verifica Redis (cache, TTL: 30s)
   ├── Cache HIT  → retorna resultado em sub-milissegundo
   └── Cache MISS → busca em paralelo (goroutines):
         ├── flag-service: GET /flags/demo
         └── targeting-service: GET /rules/demo

2. Lógica de avaliação:
   - flag.is_enabled == false? → retorna false
   - Calcula: hash(user_id + flag_name) % 100 < porcentagem?
   - → true ou false

3. Salva no Redis (TTL: 30 segundos)
4. Publica evento no Service Bus (goroutine separada, sem bloquear a resposta)
```

**Hash determinístico:** `hash(user_id + flag_name) % 100` garante que o mesmo usuário sempre recebe o mesmo resultado, independente de quantas réplicas estão rodando e sem precisar armazenar estado.

**Banco de dados:** Redis (cache) — sem PostgreSQL

---

### analytics-service · Python · porta 8005

Worker assíncrono que consome eventos do Azure Service Bus e grava no Cosmos DB.

- Roda duas threads em paralelo:
  - Thread principal: Flask servindo só `/health` (para os probes do Kubernetes)
  - Thread background: loop infinito consumindo mensagens do Service Bus
- Padrão de confiabilidade: só confirma (`complete_message`) após gravar no Cosmos DB com sucesso — se o serviço cair antes de confirmar, o lock expira (1 min) e a mensagem volta para a fila automaticamente (at-least-once delivery)

**Banco de dados:** Azure Cosmos DB (`analyticsdb` / container `analytics-events`, partition key: `/flag_name`)

---

## Os 3 data stores — propósitos distintos

| Store | Tipo | Usado por | Por que |
|---|---|---|---|
| PostgreSQL | Relacional | auth, flag, targeting | Schema definido, transactions ACID, consistência forte |
| Redis | Cache in-memory | evaluation | Sub-milissegundo, hot path com milhares de req/s |
| Cosmos DB | NoSQL | analytics | Alto volume, schema variável, sem joins |

---

## Infraestrutura Azure (deploy em produção)

| Recurso | Função |
|---|---|
| AKS | Orquestração Kubernetes |
| ACR | Registro privado de imagens Docker |
| Application Gateway + AGIC | Ingress gerenciado (L7) |
| Azure Database for PostgreSQL ×3 | auth_db, flags_db, targeting_db |
| Azure Cache for Redis | Cache do evaluation-service |
| Azure Service Bus | Fila `togglemasterqueue` (evaluation → analytics) |
| Azure Cosmos DB (serverless) | Eventos de analytics |

---

## Como rodar localmente

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e Docker Compose
- Conta Azure com Service Bus e Cosmos DB configurados
- Arquivo `.env` na raiz (veja `.env.example`)

### Configuração

```bash
# Clone o repositório
git clone https://github.com/juansrodrigues/togglemaster-microservices.git
cd togglemaster-microservices

# Crie o .env com suas credenciais Azure
cp .env.example .env
# Edite o .env com seus valores reais
```

### Subindo o ambiente

```bash
docker-compose up -d

# Verifica se todos os containers estão rodando
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Todos os containers devem aparecer com status `Up` ou `healthy`.

### Testando o fluxo completo

```bash
# 1. Health check de todos os serviços
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health

# 2. Criar API key
curl -s -X POST http://localhost:8001/admin/keys \
  -H "Authorization: Bearer SUA_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "minha-key"}' | python3 -m json.tool

# 3. Criar feature flag (use a tm_key_ retornada acima)
curl -s -X POST http://localhost:8002/flags \
  -H "Authorization: Bearer tm_key_..." \
  -H "Content-Type: application/json" \
  -d '{"name": "demo", "is_enabled": true}' | python3 -m json.tool

# 4. Criar regra de segmentação (50% dos usuários)
curl -s -X POST http://localhost:8003/rules \
  -H "Authorization: Bearer tm_key_..." \
  -H "Content-Type: application/json" \
  -d '{"flag_name": "demo", "is_enabled": true, "rules": {"type": "PERCENTAGE", "value": 50}}' | python3 -m json.tool

# 5. Avaliar (retorna true ou false)
curl "http://localhost:8004/evaluate?user_id=user-123&flag_name=demo"

# 6. Mesmo user_id sempre retorna o mesmo resultado (hash determinístico)
curl "http://localhost:8004/evaluate?user_id=user-123&flag_name=demo"
```

---

## Estrutura do repositório

```
togglemaster-microservices/
├── analytics-service/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── auth-service/
│   ├── Dockerfile
│   ├── db/init.sql
│   ├── go.mod
│   ├── handlers.go
│   ├── key.go
│   └── main.go
├── evaluation-service/
│   ├── Dockerfile
│   ├── evaluator.go
│   ├── go.mod
│   ├── handlers.go
│   ├── main.go
│   ├── servicebus.go
│   └── types.go
├── flag-service/
│   ├── Dockerfile
│   ├── db/init.sql
│   ├── app.py
│   └── requirements.txt
├── targeting-service/
│   ├── Dockerfile
│   ├── db/init.sql
│   ├── app.py
│   └── requirements.txt
├── docker-compose.yaml
├── .env.example
└── README.md
```

---

## Variáveis de ambiente

Veja `.env.example` para a lista completa. As principais:

| Variável | Usado por | Descrição |
|---|---|---|
| `MASTER_KEY` | auth-service | Senha para criar novas API keys |
| `SERVICE_BUS_CONNECTION_STRING` | evaluation, analytics | Connection string do Azure Service Bus |
| `SERVICE_BUS_QUEUE_NAME` | evaluation, analytics | Nome da fila (ex: `togglemaster-events`) |
| `COSMOS_ENDPOINT` | analytics | Endpoint do Cosmos DB |
| `COSMOS_KEY` | analytics | Chave de acesso do Cosmos DB |
| `SERVICE_API_KEY` | evaluation | API key para chamadas internas ao flag e targeting |

---

## Decisões técnicas

**Por que hash determinístico no evaluation-service?**
`hash(user_id + flag_name) % 100` garante que o mesmo usuário sempre recebe o mesmo resultado sem precisar armazenar estado. Com 10 réplicas do evaluation-service, todas calculam exatamente o mesmo resultado para o mesmo usuário sem coordenação entre si.

**Por que concatenar user_id + flag_name?**
Se usássemos só o user_id, o mesmo usuário estaria sempre no mesmo bucket para todas as flags — veria todas as features novas ou nenhuma. Com a concatenação, cada par usuário+flag tem um bucket independente.

**Por que migrar de AWS para Azure?**
O código original usava AWS SQS e DynamoDB (boto3/aws-sdk-go). Migramos para Azure Service Bus e Cosmos DB para manter a arquitetura 100% num único provedor, aproveitando a integração nativa com AKS e ACR.

**Por que gunicorn em vez do servidor Flask padrão?**
O servidor de desenvolvimento do Flask não é adequado para produção — processa uma requisição por vez. O gunicorn sobe múltiplos workers em paralelo, suportando carga real.

---

## Tech stack

![Go](https://img.shields.io/badge/Go-1.22-00ADD8?style=flat&logo=go)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat&logo=python)
![Docker](https://img.shields.io/badge/Docker-multi--stage-2496ED?style=flat&logo=docker)
![Azure](https://img.shields.io/badge/Azure-AKS%20%7C%20Service%20Bus%20%7C%20Cosmos%20DB-0078D4?style=flat&logo=microsoft-azure)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat&logo=redis)

---

*POSTECH/FIAP — DevOps & Cloud Architecture — Fase 2*


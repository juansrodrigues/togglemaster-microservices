import json
import logging
import os
import sys
import threading
import time
import uuid

from azure.servicebus import ServiceBusClient
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
from dotenv import load_dotenv
from flask import Flask, jsonify

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

load_dotenv()

# --- Configuração ---
SERVICE_BUS_CONNECTION_STRING = os.getenv("SERVICE_BUS_CONNECTION_STRING")
SERVICE_BUS_QUEUE_NAME = os.getenv("SERVICE_BUS_QUEUE_NAME", "togglemaster-events")
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "analyticsdb")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "analytics-events")

# Valida variáveis obrigatórias
missing = [
    name for name, val in [
        ("SERVICE_BUS_CONNECTION_STRING", SERVICE_BUS_CONNECTION_STRING),
        ("COSMOS_ENDPOINT", COSMOS_ENDPOINT),
        ("COSMOS_KEY", COSMOS_KEY),
    ] if not val
]
if missing:
    log.critical(f"Variáveis obrigatórias não definidas: {', '.join(missing)}")
    sys.exit(1)

# --- Clientes Azure ---
try:
    cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    database = cosmos_client.get_database_client(COSMOS_DATABASE)
    container = database.get_container_client(COSMOS_CONTAINER)
    log.info(f"Cliente Cosmos DB inicializado. Database: {COSMOS_DATABASE}, Container: {COSMOS_CONTAINER}")
except Exception as e:
    log.critical(f"Erro ao inicializar Cosmos DB: {e}")
    sys.exit(1)


# --- Worker do Azure Service Bus ---

def process_message(message):
    """
    Processa uma mensagem da fila e insere no Cosmos DB.
    
    Padrão de confiabilidade (at-least-once delivery):
    - Só confirma (complete) APÓS gravar com sucesso no Cosmos DB
    - Se falhar antes do complete, o lock expira (1 min) e a mensagem
      volta para a fila automaticamente — nenhum dado é perdido
    
    Analogia de dados: é como o checkpoint do Spark Structured Streaming —
    você só avança o offset depois que o dado foi persistido com sucesso.
    """
    try:
        body = json.loads(str(message))
        log.info(f"Processando: Flag={body.get('flag_name')}, User={body.get('user_id')}")

        # UUID garante unicidade do documento no Cosmos DB
        event_id = str(uuid.uuid4())

        # Cosmos DB usa JSON puro — muito mais natural que o DynamoDB
        # que exige tipos explícitos como {"S": "valor"}, {"BOOL": true}
        item = {
            "id": event_id,           # obrigatório no Cosmos DB
            "event_id": event_id,
            "user_id": body["user_id"],
            "flag_name": body["flag_name"],   # partition key — deve existir!
            "result": body["result"],
            "timestamp": body["timestamp"],
        }

        container.create_item(body=item)
        log.info(f"Evento {event_id} (Flag: {body['flag_name']}) salvo no Cosmos DB.")

        # Retorna True = processou com sucesso = pode confirmar na fila
        return True

    except json.JSONDecodeError:
        log.error("Mensagem malformada (poison pill) — descartando")
        return True  # descarta para não travar a fila
    except cosmos_exceptions.CosmosHttpResponseError as e:
        log.error(f"Erro ao gravar no Cosmos DB: {e}")
        return False  # não confirma — mensagem volta para a fila
    except Exception as e:
        log.error(f"Erro inesperado: {e}")
        return False


def service_bus_worker_loop():
    """
    Loop principal do worker.
    
    Diferença Service Bus vs SQS:
    - SQS: você recebe e precisa deletar explicitamente com ReceiptHandle
    - Service Bus: mensagem fica locked durante processamento.
      complete_message() = confirma sucesso (remove da fila)
      abandon_message()  = devolve para a fila (será reprocessada)
    """
    log.info("Iniciando worker do Azure Service Bus...")

    while True:
        try:
            with ServiceBusClient.from_connection_string(
                SERVICE_BUS_CONNECTION_STRING
            ) as client:
                with client.get_queue_receiver(
                    queue_name=SERVICE_BUS_QUEUE_NAME,
                    max_wait_time=20,  # long-polling: espera até 20s por mensagens
                ) as receiver:
                    log.info("Conectado ao Service Bus. Aguardando mensagens...")

                    for message in receiver:
                        success = process_message(message)

                        if success:
                            receiver.complete_message(message)
                            log.info("Mensagem confirmada (removida da fila).")
                        else:
                            receiver.abandon_message(message)
                            log.warning("Mensagem devolvida para a fila (será reprocessada).")

        except Exception as e:
            log.error(f"Erro no worker do Service Bus: {e}")
            log.info("Aguardando 10s antes de reconectar...")
            time.sleep(10)


# --- Flask (apenas health check para o Kubernetes) ---
app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def start_worker():
    worker_thread = threading.Thread(target=service_bus_worker_loop, daemon=True)
    worker_thread.start()
    log.info("Worker do Service Bus iniciado em background.")


start_worker()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8005))
    app.run(host="0.0.0.0", port=port, debug=False)

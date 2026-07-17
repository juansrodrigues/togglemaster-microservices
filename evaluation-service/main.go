package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/messaging/azservicebus"
	"github.com/go-redis/redis/v8"
	"github.com/joho/godotenv"
)

var ctx = context.Background()

// App struct — ServiceBusClient substitui SqsSvc do original.
// Redis, HttpClient e URLs dos serviços permanecem iguais.
type App struct {
	RedisClient         *redis.Client
	ServiceBusClient    *azservicebus.Client
	ServiceBusQueueName string
	HttpClient          *http.Client
	FlagServiceURL      string
	TargetingServiceURL string
}

func main() {
	_ = godotenv.Load()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8004"
	}

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		log.Fatal("REDIS_URL deve ser definida")
	}

	flagSvcURL := os.Getenv("FLAG_SERVICE_URL")
	if flagSvcURL == "" {
		log.Fatal("FLAG_SERVICE_URL deve ser definida")
	}

	targetingSvcURL := os.Getenv("TARGETING_SERVICE_URL")
	if targetingSvcURL == "" {
		log.Fatal("TARGETING_SERVICE_URL deve ser definida")
	}

	// Service Bus é opcional — se não configurado, eventos são apenas logados.
	// O serviço principal (avaliar flags) funciona normalmente sem ele.
	serviceBusConnStr := os.Getenv("SERVICE_BUS_CONNECTION_STRING")
	serviceBusQueueName := os.Getenv("SERVICE_BUS_QUEUE_NAME")
	if serviceBusConnStr == "" {
		log.Println("Atenção: SERVICE_BUS_CONNECTION_STRING não definida. Eventos serão apenas logados.")
	}

	// --- Redis ---
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("Erro ao parsear REDIS_URL: %v", err)
	}
	rdb := redis.NewClient(opt)
	if _, err := rdb.Ping(ctx).Result(); err != nil {
		log.Fatalf("Não foi possível conectar ao Redis: %v", err)
	}
	log.Println("Conectado ao Redis com sucesso!")

	// --- Azure Service Bus ---
	var sbClient *azservicebus.Client
	if serviceBusConnStr != "" {
		sbClient, err = azservicebus.NewClientFromConnectionString(serviceBusConnStr, nil)
		if err != nil {
			log.Fatalf("Erro ao criar cliente do Service Bus: %v", err)
		}
		log.Printf("Cliente Azure Service Bus inicializado. Fila: %s", serviceBusQueueName)
	}

	httpClient := &http.Client{Timeout: 5 * time.Second}

	app := &App{
		RedisClient:         rdb,
		ServiceBusClient:    sbClient,
		ServiceBusQueueName: serviceBusQueueName,
		HttpClient:          httpClient,
		FlagServiceURL:      flagSvcURL,
		TargetingServiceURL: targetingSvcURL,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.healthHandler)
	mux.HandleFunc("/evaluate", app.evaluationHandler)

	log.Printf("Serviço de Avaliação (Go) rodando na porta %s", port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatal(err)
	}
}

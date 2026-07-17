package main

// servicebus.go — substitui sqs.go
// Publica eventos de avaliação no Azure Service Bus.

import (
	"context"
	"encoding/json"
	"log"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/messaging/azservicebus"
)

// EvaluationEvent — estrutura idêntica ao sqs.go original.
// Só muda o transporte (SQS → Service Bus), não o formato JSON.
// O analytics-service recebe exatamente o mesmo payload de antes.
type EvaluationEvent struct {
	UserID    string    `json:"user_id"`
	FlagName  string    `json:"flag_name"`
	Result    bool      `json:"result"`
	Timestamp time.Time `json:"timestamp"`
}

// sendEvaluationEvent publica um evento no Azure Service Bus.
// Chamado como goroutine no handler — não bloqueia a resposta HTTP.
func (a *App) sendEvaluationEvent(userID, flagName string, result bool) {
	if a.ServiceBusClient == nil || a.ServiceBusQueueName == "" {
		log.Printf("[SERVICEBUS_DISABLED] Evento: User='%s', Flag='%s', Result='%t'",
			userID, flagName, result)
		return
	}

	event := EvaluationEvent{
		UserID:    userID,
		FlagName:  flagName,
		Result:    result,
		Timestamp: time.Now().UTC(),
	}

	body, err := json.Marshal(event)
	if err != nil {
		log.Printf("Erro ao serializar evento: %v", err)
		return
	}

	sender, err := a.ServiceBusClient.NewSender(a.ServiceBusQueueName, nil)
	if err != nil {
		log.Printf("Erro ao criar sender do Service Bus: %v", err)
		return
	}
	defer sender.Close(context.Background())

	contentType := "application/json"
	message := &azservicebus.Message{
		Body:        body,
		ContentType: &contentType,
	}

	err = sender.SendMessage(context.Background(), message, nil)
	if err != nil {
		log.Printf("Erro ao enviar para Service Bus: %v", err)
	} else {
		log.Printf("Evento enviado ao Service Bus (Flag: %s, User: %s)", flagName, userID)
	}
}

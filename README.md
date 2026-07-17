Esse README tem o objetivo de resumir o Tech Challenge da Fase 2

# PROJETO TC F2
O projeto dessa fase é subir uma aplicação de 5 microsserviço, que são:
  - auth-service: Responsável pelo gerenciamento de das chaves API e autenticação do sistemas.
  - flag-service: CRUD das feature-flags.
  - targeting-service: Gerencia regras complexas de segmentação.
  - evaluation-service: O "caminho quente" (hot path) de alta performance que retorna a decisão final (true/false).
  - analytics-service: Responsável pelo consumo de eventos de uma fila e salva os dados da análise no projeto.


## Agora será explicado com mais detalhes cada microsserviço.

# auth-service
Ele é responnsavel pela autenticação de usuários e gerenciamento das chaves API.

É usado junto com o evaluations-service no momento da inserção de usuário e senha.

Ele é construído em GO divido em 3 partes:
  - handles: responsável pela parte de gerir e salvar as chaves API.
  - key: Responsável de criação de chaves API.
  - main: faz a gestão das rotas API, além de iniciar a comunicação do banco, em resumo, 
  ele faz a ponte dos requests do evaluation-service com o banco de dados, enviando os dados necessários.


# flag-service
É um CRUD das feature-flags que consiste em um único arquivo de código, ele faz toda a gestão das flags além da autenticação.

Ele é construído em Python utilizando bibliotecas como o psycopg2 para comunicação com o postegresql e o flask para uso em ambientes web.


# targeting-service


# evaluation-service

# analytics-service



Foi criado o Dockerfile para cada microsserviço além de um docker-compose único para o projeto


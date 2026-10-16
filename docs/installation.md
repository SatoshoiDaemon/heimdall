# Instalação

## Discord

1. Crie a aplicação e o bot no Developer Portal.
2. Em Bot, habilite Server Members Intent e Message Content Intent.
3. Em OAuth2, use `bot` e `applications.commands` para gerar o convite.
4. Conceda apenas os recursos usados: View Channels, Send Messages, Embed Links,
   Attach Files, Read Message History, Manage Messages, Ban Members, Kick Members,
   Moderate Members e Manage Roles.
5. Coloque o cargo do Heimdall acima dos alvos e do cargo de verificado.

As permissões de canal também se aplicam. O bot não precisa de Administrator.
O moderador pode ter uma permissão Discord correspondente ou uma concessão
RBAC. O bot sempre precisa da permissão Discord necessária para executar.

## Docker Compose

```sh
cp .env.example .env
# Edite BOT_TOKEN.
docker compose up -d --build
docker compose logs -f bot
docker compose ps
```

O serviço `mongo-init` inicializa um replica set de um membro e espera pelo
primário. Isso permite transações; não é uma topologia de alta disponibilidade.
`mongo-data` guarda o banco e `redis-data` o AOF. `docker compose down` preserva
ambos. Faça backup antes de remover volumes.

O bot roda com UID 10001, filesystem somente leitura e `/tmp` temporário.
O healthcheck exige heartbeat recente do gateway, MongoDB e Redis. A imagem
não publica endpoint HTTP.

## Python local

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python run.py
```

No Windows, ative com `.venv\Scripts\activate`. Configure MongoDB e Redis
acessíveis. MongoDB standalone funciona com recuperação de gravações parciais;
use um replica set para atomicidade entre coleções.

| Variável | Obrigatória | Exemplo/padrão |
| --- | --- | --- |
| BOT_TOKEN | sim | token da aplicação |
| MONGO_URI | sim | `mongodb://localhost:27017/?replicaSet=rs0` |
| MONGO_DB_NAME | sim | `heimdall` |
| REDIS_URI | sim | `redis://localhost:6379/0` |
| CAPTCHA_TIMEOUT_SECONDS | não | `300` (1–86400) |
| LOG_WORKER_INTERVAL_SECONDS | não | `5` (1–3600) |
| GUILD_ID | não | reservado; comandos são sincronizados globalmente |

Variáveis no ambiente substituem valores de `.env`. No Compose as URIs dos
serviços internos são definidas em `environment`. Para bancos externos,
altere esses valores no arquivo Compose. Não adicione `.env` ao Git.

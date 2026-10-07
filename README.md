# Heimdall

Heimdall é um bot de Discord focado em moderação e gerenciamento de membros.
O projeto está sendo desenvolvido em Python com uma arquitetura assíncrona e
separação entre comandos, serviços, repositórios e infraestrutura.

## Estado atual

Esta é a fundação inicial do projeto. Já existem componentes para configuração
por servidor, auditoria, antiabuso, CAPTCHA, RBAC, MongoDB e Redis. A moderação
manual agora inclui advertências, banimentos, expulsões, timeout, purge, notas,
cases e histórico. O painel central com Components V2, o AutoMod configurável e
a engine de automações serão desenvolvidos nas próximas fases.

Ficam fora do escopo do Heimdall anti-raid, análise de intenção, IA para decidir
punições e qualquer tentativa de transformá-lo em um sistema de segurança
coordenada.

## Requisitos

- Python 3.11, 3.12 ou 3.13
- MongoDB
- Redis
- Um bot criado no [Discord Developer Portal](https://discord.com/developers/applications)

O bot precisa dos intents `Server Members Intent` e `Message Content Intent`
habilitados no Developer Portal para os recursos atuais.

## Instalação local

```bash
git clone git@github.com:SatoshoiDaemon/heimdall.git
cd heimdall

python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\\Scripts\\activate  # Windows

python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Preencha `.env` com valores reais antes de iniciar o bot. O arquivo `.env` é
ignorado pelo Git e nunca deve ser publicado.

## Configuração

Variáveis obrigatórias:

```dotenv
BOT_TOKEN=seu_token
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=heimdall
REDIS_URI=redis://localhost:6379/0
```

Variáveis opcionais:

```dotenv
CAPTCHA_TIMEOUT_SECONDS=300
LOG_WORKER_INTERVAL_SECONDS=5
# GUILD_ID=123456789012345678
```

O processo valida a configuração antes de tentar conectar aos serviços. Valores
ausentes ou inválidos fazem o processo terminar com uma mensagem objetiva.

## Execução

```bash
python run.py
```

## Testes e qualidade

```bash
python -m pytest
python -m ruff check .
python -m compileall -q run.py src tests
```

A CI do GitHub Actions executa esses checks em pull requests e em pushes para
`main`, usando Python 3.11, 3.12 e 3.13.

## Moderação manual

O Cog de moderação disponibiliza `/warn`, `/unwarn`, `/warnings`, `/ban`,
`/unban`, `/kick`, `/timeout`, `/untimeout`, `/mute`, `/unmute`, `/purge`,
`/note`, `/notes`, `/history` e `/case`.

As ações são registradas em cases numerados por servidor. `mute` é um alias de
timeout e as operações reversíveis criam um novo case relacionado ao case
original. Consultas e notas são respondidas de forma efêmera para moderadores.

## Estrutura

- `src/cogs/`: comandos e listeners do Discord.
- `src/core/`: configuração, bot, conexões, eventos e logs.
- `src/dtos/`: objetos de transferência internos.
- `src/middlewares/`: verificações de acesso.
- `src/models/`: modelos de domínio e documentos MongoDB.
- `src/repositories/`: acesso às coleções persistentes.
- `src/services/`: regras de negócio e integrações.
- `src/utils/`: utilitários de apresentação.
- `tests/`: testes unitários sem dependência de serviços externos.

## Licença

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).

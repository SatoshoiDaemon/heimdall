# Heimdall

Bot de moderação para Discord em Python, com persistência em MongoDB.
O código-fonte completo é implantado em uma PaaS ou hospedagem de bots:
a plataforma instala as dependências e executa um único processo Python.

Versão candidata: **0.2.0rc2**. A release estável depende da aceitação em uma
hospedagem gerenciada e servidor Discord de teste, conforme
[docs/releasing.md](docs/releasing.md).

## Executar

Use Python **3.11–3.13**. Configure as variáveis de ambiente abaixo e execute:

```sh
python -m pip install -r requirements.txt
python run.py
```

```dotenv
BOT_TOKEN=token_da_aplicacao
MONGO_URI=mongodb://seu-servidor:27017
MONGO_DB_NAME=heimdall
```

Para desenvolvimento local, copie `.env.example` para `.env` e preencha os
valores. Em PaaS, use o painel de variáveis de ambiente da hospedagem.
Envie `run.py`, `requirements.txt` e todo o diretório `src/`, preservando a
estrutura do repositório. Instalar ferramentas de desenvolvimento não é
necessário para executar o bot.

O bot não abre porta HTTP nem depende de disco persistente local, acesso root
ou processos auxiliares. Seus únicos serviços externos são Discord e MongoDB.

## Configurar no Discord

1. Crie uma aplicação no [Discord Developer Portal](https://discord.com/developers/applications).
2. Habilite **Server Members Intent** e **Message Content Intent**.
3. Convide o bot com os escopos `bot` e `applications.commands`.
4. Conceda as permissões usadas e posicione o cargo do bot acima dos alvos.
5. Abra `/config` para configurar auditoria, cargo de verificado, AutoMod e exceções.

A lista de permissões e as instruções de deploy estão em
[instalação](docs/installation.md). Exemplos de regras e comandos estão em
[configuração](docs/configuration.md).

## Funcionalidades

- Moderação manual: advertências, banimentos, expulsões, timeout, purge e notas.
- Cases numerados por servidor, reversões, recuperação de operações incompletas
  e histórico paginado diretamente no MongoDB.
- AutoMod: Anti-Spam, Anti-Link/convites, Anti-Mention, URLs, palavras e repetição.
- Ações por regra: excluir, advertir ou aplicar timeout; exceções por cargo/canal.
- CAPTCHA com concessão real do cargo, expiração, limite de tentativas e recuperação.
- Painel por categorias e RBAC administrado pelo Discord.
- Auditoria persistida antes do envio e worker assíncrono com tentativas limitadas.

| Área | Comandos |
| --- | --- |
| Advertências | `/warn`, `/warnings`, `/unwarn` |
| Punições | `/ban`, `/unban`, `/kick`, `/timeout`, `/untimeout`, `/mute`, `/unmute` |
| Organização | `/purge`, `/note`, `/notes` |
| Consulta | `/history`, `/case` |
| Administração | `/config`, `/rbac` |
| Verificação | `/manual_verify`, `/solve_captcha` |

O RBAC permite delegar comandos, preservando a hierarquia do autor e do bot.
O dono do servidor é protegido; administradores não podem receber timeout.
`mute` usa o timeout nativo. Consultas de moderação são efêmeras.

## Arquitetura

Cogs recebem comandos, interações e eventos. Serviços aplicam as regras de
moderação; repositórios acessam o MongoDB; modelos validam os dados.
EventBus, cache e locks são componentes internos do mesmo processo.

| Persistido no MongoDB | Temporário em memória |
| --- | --- |
| Configurações, RBAC, cases e contadores | Cache com TTL e invalidação |
| Advertências, notas e punições | Janelas de spam e cooldowns |
| Sessões CAPTCHA com expiração | Locks asyncio por recurso |
| Eventos de auditoria e falhas de entrega | Fila limitada para o worker de auditoria |

Execute **um processo do Heimdall por aplicação/bot**; os shards do
AutoShardedBot compartilham esse processo. Reinícios limpam estruturas
transitórias, preservam sessões CAPTCHA e recuperam auditoria/cases no MongoDB.

## Desenvolvimento

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -m 'not integration' --cov
```

Integração usa uma instância MongoDB configurada. Veja
[CONTRIBUTING.md](CONTRIBUTING.md). A CI testa Python 3.11/3.12/3.13,
MongoDB standalone e replica set, além da instalação limpa das dependências
de produção.

[Operação e recuperação](docs/operations.md) ·
[Changelog](CHANGELOG.md) · [MIT](LICENSE)

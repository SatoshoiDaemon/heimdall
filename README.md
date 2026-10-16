# Heimdall

Bot open source de moderação para Discord, em Python, MongoDB e Redis.
Versão de desenvolvimento: **0.2.0rc1**. A publicação estável depende dos
critérios em [docs/releasing.md](docs/releasing.md).

## Recursos

- Advertências, bans, expulsões, timeouts, purge, notas e cases por servidor.
- AutoMod com regras de spam ponderado, repetição, menções, palavras, URLs e
  convites; ações individuais de advertência, exclusão ou timeout.
- CAPTCHA que concede o cargo configurado, com sessão recuperável em falhas.
- Painel `/config` por categorias e `/rbac` para administrar permissões.
- Histórico paginado no banco com filtros por usuário, moderador, ação,
  origem e período.
- Intenções persistentes, transações em replica sets, reconciliação após
  reinícios e auditoria com outbox, Redis Streams, confirmação e fila de falhas.
- Docker sem root, Compose, logs JSON, métricas e healthcheck.

O foco é moderação determinística. Anti-raid, inferência de intenção e punições
por IA ficam fora do escopo.

## Iniciar

Crie uma aplicação no [Discord Developer Portal](https://discord.com/developers/applications).
Habilite **Server Members Intent** e **Message Content Intent** e convide o bot
com os escopos `bot` e `applications.commands`.

```sh
git clone https://github.com/SatoshoiDaemon/heimdall.git
cd heimdall
cp .env.example .env
# Preencha BOT_TOKEN em .env.
docker compose up -d --build
```

O Compose inicia MongoDB em replica set e Redis com persistência AOF, sem
publicar portas dos bancos. Após o bot conectar, abra `/config`, escolha o canal
de auditoria e o cargo de verificado e configure as regras do AutoMod.

Para execução local e permissões, veja [instalação](docs/installation.md).
Para regras, exemplos e diagnóstico, veja [configuração](docs/configuration.md).

## Comandos

| Área | Comandos |
| --- | --- |
| Advertências | `/warn`, `/warnings`, `/unwarn` |
| Punições | `/ban`, `/unban`, `/kick`, `/timeout`, `/untimeout`, `/mute`, `/unmute` |
| Organização | `/purge`, `/note`, `/notes` |
| Auditoria | `/history`, `/case` |
| Administração | `/config`, `/rbac` |
| Verificação | `/manual_verify`, `/solve_captcha` |

`mute` usa o timeout nativo do Discord. Consultas de moderação são efêmeras.
Permissões nativas ou RBAC liberam comandos; a hierarquia continua obrigatória,
inclusive para administradores. O dono ignora apenas a própria comparação de
cargo; nunca a hierarquia do bot. Administradores não podem receber timeout.

## Desenvolvimento

Python 3.11–3.13:

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -m 'not integration' --cov
```

A CI também executa testes de integração com MongoDB replica set e Redis reais,
constrói a imagem e verifica o usuário sem root. Instruções completas em
[CONTRIBUTING.md](CONTRIBUTING.md).

## Garantias operacionais

Os cases são a fonte de verdade. Uma ação externa recebe intenção persistente
antes de ser enviada ao Discord. Operações idempotentes e projeções incompletas
são recuperadas pelo worker. Purges e expulsões interrompidos em ponto ambíguo
ficam como `uncertain` para revisão, evitando repetição destrutiva.

A auditoria tem entrega **pelo menos uma vez**: falha entre envio e confirmação
pode repetir uma mensagem, identificada pelo mesmo ID. Após cinco falhas, o
registro permanece na outbox com `dead=true` e na coleção `audit_failures`.
Eventos sem canal configurado recebem resultado `unconfigured`.

Consulte [operação e recuperação](docs/operations.md) para estados, fila de
falhas, métricas, migração e limites.

## Licença

[MIT](LICENSE).

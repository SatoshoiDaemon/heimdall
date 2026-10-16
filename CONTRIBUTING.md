# Contribuindo

Use Python 3.11–3.13 e instale `requirements-dev.txt` em um ambiente virtual.
A arquitetura separa Cogs (Discord), serviços (regras), repositórios (MongoDB)
e infraestrutura (conexões, eventos e logs).

## Verificações

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m compileall -q run.py src tests scripts
python -m pytest -m 'not integration' --cov
```

A cobertura mínima inicial é 65% da aplicação inteira. Não exclua módulos de
produção para melhorar o número. Prefira testes de comportamento observável,
falhas e concorrência. A checagem de tipos é progressiva: modelos, DTOs,
configuração e métricas são a base inicial; amplie o escopo conforme tipar os
outros módulos.

## Integração real

Inicie um MongoDB replica set e um Redis dedicado. Os testes apagam o DB Redis
selecionado e criam/removem bancos MongoDB temporários. Não use dados reais.
A receita exata de inicialização também está em `.github/workflows/ci.yml`.

```sh
HEIMDALL_INTEGRATION=1 \
TEST_MONGO_URI='mongodb://localhost:27017/?replicaSet=rs0' \
TEST_REDIS_URI='redis://localhost:6379/15' \
python -m pytest -m integration -v
```

A suíte cobre Lua real, expiração, concorrência dos contadores, rollback de
transações, persistência parcial, locks e retomada de mensagens pendentes.
Testes unitários usam Redis/Mongo em memória; eles complementam a suíte real.
Discord é substituído por um adaptador de teste para não punir usuários reais.
Valide alterações de API do Discord em um servidor de teste antes da release.

Para medir custo Redis:

```sh
TEST_REDIS_URI=redis://localhost:6379/15 python -m scripts.benchmark_redis
```

## Pull requests

Descreva o problema, comportamento final, testes e mudanças de configuração.
Mantenha intents, estados de recuperação, hierarquia e semântica de confirmação
explícitos. Mudanças em schemas devem preservar documentos existentes ou
incluir migração. Atualize CHANGELOG e documentação quando o comportamento
exposto mudar. Nunca registre tokens, URIs com senha ou códigos CAPTCHA.

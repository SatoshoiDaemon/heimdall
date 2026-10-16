# Contribuindo

Use Python 3.11–3.13. Instale `requirements-dev.txt` em um ambiente virtual;
`requirements.txt` contém apenas dependências de produção. Cogs cuidam do
Discord, serviços das regras de negócio e repositórios do MongoDB.

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m compileall -q run.py src tests scripts
python -m pytest -m 'not integration' --cov
```

Os testes unitários não precisam de serviços externos. Usam MongoDB em memória
para persistência, mocks da API Discord e as próprias estruturas locais do bot.
A cobertura mínima é 65% da aplicação inteira. Não exclua módulos de produção
para melhorar o número. Tipos são verificados progressivamente em modelos,
DTOs, configuração e métricas.

## Integração

Aponte os testes para uma instância MongoDB acessível:

```sh
HEIMDALL_INTEGRATION=1 \
TEST_MONGO_URI='mongodb://localhost:27017' \
python -m pytest -m integration -v
```

A suíte cria e remove bancos temporários com prefixo `heimdall_test_`;
não apaga outras bases. Use um usuário autorizado a criar bancos de teste.
Standalone é suportado; se a instância for replica set, os testes também
verificam rollback transacional. A CI testa os dois modos iniciando um
binário temporário do MongoDB, sem depender de containers.

Para apenas rodar o bot, os comandos continuam:

```sh
python -m pip install -r requirements.txt
python run.py
```

## Alterações

Priorize testes de CAPTCHA, AutoMod, hierarquia/RBAC, paginação, cases,
auditoria, concorrência e lifecycle. Locks e caches são locais a um único
processo; não introduza requisitos de infraestrutura fora do modelo PaaS.

Descreva o problema, comportamento final e validação no PR. Mantenha migrações
compatíveis e atualize documentação/changelog. Não registre tokens ou
respostas CAPTCHA. Para alterações de interface, confira limites de embeds,
labels e componentes e valide a interação real em um servidor de teste.

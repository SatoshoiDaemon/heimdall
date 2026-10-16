# Changelog

## 0.2.0rc2 — 2026-10-16

### Realinhamento para bot Discord em PaaS

- Distribuição por código-fonte completo: requirements.txt e python run.py.
- Removidos Dockerfile, Compose, healthcheck de arquivo e benchmark de infraestrutura.
- Removidos o cliente Redis, sua dependência, variável de ambiente e serviços na CI.
- Configuração/RBAC usam cache local com TTL, limites e invalidação após alterações.
- Locks usam asyncio.Lock por recurso e são removidos quando ociosos.
- Anti-Spam usa janela deslizante em memória, pontuação incremental, deduplicação
  de mensagens e cooldown; limites e limpeza mantêm o consumo previsível.
- CAPTCHA persiste no MongoDB com hash, TTL, cinco tentativas e recuperação.
- Auditoria persiste no MongoDB antes de agendar uma asyncio.Queue limitada;
  o worker recupera pendências após reinício e mantém tentativas/falhas.
- Padronizadas páginas de warnings, notes e history diretamente no repositório,
  incluindo conjuntos grandes, páginas inexistentes e botões.
- Inicialização interrompe em falhas críticas; SIGTERM/SIGINT encerram workers e
  conexões. Logs seguem para stdout, sem depender de porta ou volume persistente.
- Preservados hierarquia/RBAC, cases numerados atomicamente, intenções,
  transações opcionais e recuperação de gravações parciais.
- CI testa Python 3.11/3.12/3.13, instalação limpa e MongoDB standalone/replica set.
- Documentação atualizada para configuração pelo Discord e hospedagem gerenciada.

### Atualização

1. Envie o código-fonte completo para a hospedagem.
2. Reinstale requirements.txt e configure BOT_TOKEN, MONGO_URI e MONGO_DB_NAME.
3. Remova REDIS_URI e a configuração anterior de containers/serviços auxiliares.
4. Execute python run.py. O bot cria os índices necessários, preserva cases,
   configurações, RBAC e auditoria já persistidos no MongoDB.
5. Caches, pontuações/cooldowns e desafios antigos que estavam somente no serviço
   removido não são importados. Gere novamente esses desafios pelo Discord.

### Publicação

A release estável aguarda a checklist de docs/releasing.md, incluindo aceitação
em hospedagem gerenciada e servidor Discord real. Nenhuma tag estável antecipada.

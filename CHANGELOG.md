# Changelog

## 0.2.0rc1 — 2026-10-16

### Corrigido

- Paginação de advertências/notas com validação da página inicial.
- CAPTCHA concede cargo, preserva sessão após falha e permite concluir após crash.
- Hierarquia do moderador, bot, owner e administradores, inclusive com RBAC.
- Intenção persistente antes de ações Discord; transações e recuperação de projeções.
- Reversões com ID determinístico e proteção contra repetição.
- Auditoria com outbox MongoDB, Redis Streams, confirmação, retries e fila de falhas.
- Anti-spam atômico, IDs sem colisões, cooldown e política explícita para falha Redis.
- Falha em Cog essencial interrompe inicialização com exit code de erro.

### Adicionado

- Consumidor AutoMod com advertência, exclusão e timeout, gerando cases automáticos.
- Regras individuais para spam, repetição, palavras, URLs, convites e menções.
- Exceções por cargo/canal e painel de configuração por categorias.
- Administração RBAC no Discord, com consulta efetiva e auditoria.
- Histórico com filtros e paginação real no banco.
- Logs JSON, métricas por processo e heartbeat de gateway/bancos.
- Docker sem root, healthcheck e Compose persistente com replica set.
- CI com integração real, imagem, cobertura e tipos progressivos.
- Benchmark comparável de Redis e documentação de instalação/contribuição/release.

### Compatibilidade

- Mantidos Python, discord.py, MongoDB, Redis e os comandos existentes.
- Mantidas flags AutoMod antigas; regras explícitas têm precedência.
- Cases antigos recebem estado completed/origem manual; a fila de logs antiga
  é migrada para a outbox. Reveja duplicatas antes de criar índices únicos.
- Auditoria tem entrega pelo menos uma vez; purge/kick ambíguos exigem revisão.

### Aceitação pendente

- Publicação estável exige a checklist de `docs/releasing.md`, incluindo um
  servidor Discord de teste. Esta candidata não cria uma tag estável.

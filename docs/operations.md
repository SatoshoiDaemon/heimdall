# Operação e recuperação

## Cases

Estados: `pending` → `applying` → `applied` → `completed`. Ações apenas no banco
saltam diretamente de pending para completed. `failed` indica uma recusa de
permissão; `uncertain` indica resultado externo ambíguo de purge/kick.
`revoked`/`active` continuam indicando reversão da punição, sem apagar o case.

A reconciliação roda a cada 20s após o gateway estar pronto. Ela usa os mesmos
locks de usuário das ações manuais, revalida hierarquia e repara projeções de
advertências, notas, timeouts e reversões. Operações em andamento mantêm lease
Redis renovável; perda da lease interrompe a execução e preserva a intenção.
Sem Redis, moderação falha de forma fechada e o detector não presume abuso.

O banco é a fonte de verdade; as coleções warns, punishments e notes são
projeções recuperáveis. Em replica sets, projeções, outbox e conclusão são
transacionais. Em standalone, esses passos podem ficar temporariamente
incompletos até a reconciliação. Nunca se promete uma transação com o Discord.

Bans verificam se o membro já está banido antes de reaplicar. Timeouts guardam
o instante final original, evitando estender a duração após reinício.
Expulsões e purges com estado `applying` após crash ficam `uncertain`. Revise
`/case`, o audit log Discord e os efeitos reais antes de intervir no banco:
se confirmar que a ação ocorreu, marque `status: applied` para concluir só a
persistência; se confirmar que não ocorreu, marque `pending` para repetir.
Casos pendentes ou incertos bloqueiam novas ações no mesmo alvo até a resolução;
a recuperação nunca reaplica uma punição antiga após uma nova. Timeouts
expirados têm suas projeções marcadas como inativas pelo worker.
Nunca reinicie um purge sem conferir o efeito anterior.

## Auditoria

A outbox MongoDB recebe um ID estável; o stream Redis `modbot:audit` distribui
IDs ao grupo `delivery`. Eventos pendentes podem ser retomados via XAUTOCLAIM.
O envio usa uma lease MongoDB de 120s e timeout de 90s. A confirmação é gravada
no banco antes do XACK/XDEL. Reespelhamento da outbox recupera perda de Redis.
Backoff exponencial e cinco tentativas limitam falhas permanentes; registros
mortos permanecem em `audit_outbox` e `audit_failures`.

Para reenviar um evento morto após corrigir canal/permissões, redefina no
registro da outbox: `attempts: 0`, `dead: false`, `delivered: false`,
`next_attempt: <agora UTC>` e remova `queued_at`, `lease_until` e `lease_token`.
Mantenha o mesmo `_id`. A coleção de falhas é um histórico; remova sua entrada
apenas após confirmar a entrega.

Sem canal configurado, eventos recebem `outcome: unconfigured` e são
confirmados explicitamente. O envio ao Discord é pelo menos uma vez: um crash
após envio e antes da confirmação pode duplicar a mensagem. O rodapé mantém o
ID para identificar essas duplicações.

Filas antigas `modbot:log_queue` são migradas com claim atômico para a outbox.
Entradas malformadas são preservadas em `modbot:legacy_log_failures`.
Cases antigos sem estado recebem `completed` e origem `manual` na inicialização.
Índices únicos detectam duplicatas preexistentes; se a criação do índice
falhar, inspecione e resolva as duplicatas antes de reiniciar.

## Métricas e diagnóstico

Logs JSON incluem guild_id, case_id, action, outcome e duração quando a operação
os possui. O snapshot periódico e `/tmp/heimdall-health.json` expõem contadores
de cases concluídos, falhas de callback/entrega, pendências, fila de falhas e
última latência de entrega. São métricas por processo, reiniciadas no restart.
O heartbeat só é escrito com gateway pronto e bancos acessíveis.

| Sintoma | Conferir |
| --- | --- |
| Comando ausente | intents, convite applications.commands, sincronização global |
| Não consegue punir | permissão do autor, bot e hierarquia; administrators não recebem timeout |
| CAPTCHA correto sem acesso | cargo configurado/gerenciável, Manage Roles, canal permitido ao cargo |
| AutoMod não age | regra habilitada, exceções, administrador/bot, cooldown, Redis e permissões |
| Auditoria sem mensagens | canal, Embed Links, outbox pending/dead e logs do worker |
| Inicialização falha | variáveis, bancos, índices e erro do Cog essencial |

## Desempenho

A versão anterior fazia quatro round trips por mensagem e transferia todos os
registros da janela ao Python. A atualização atômica faz um EVAL e mantém a
janela limitada pelo limiar, sem transferir registros. RBAC consulta grants
em MongoDB sem cache de autorização e agrupa os cargos numa única consulta;
revogações não dependem de TTL. Cache de configuração usa revisão autoritativa
e TTL de uma hora. Invalidações por padrão usam SCAN, nunca KEYS.

Meça no seu Redis com `TEST_REDIS_URI=redis://localhost:6379/15 python -m
scripts.benchmark_redis`; use um banco dedicado a testes. A CI gera um artefato
JSON com mediana/p95 anteriores e atuais. Resultados dependem da latência de
rede; não são usados como asserções frágeis de teste.

Não há coleta automática de telemetria externa nem armazenamento de métricas
históricas. Defina retenção/backups do MongoDB conforme sua operação; outbox,
cases e fila de falhas não são apagados automaticamente.

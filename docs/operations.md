# Operação e recuperação

## Modelo de execução

Um processo Python por bot/aplicação, incluindo todos os shards gerenciados
pelo discord.py. Cache, janelas de spam, cooldowns, locks e fila local não são
compartilhados entre processos. Não configure múltiplas réplicas simultâneas
do mesmo bot. A hospedagem pode reiniciar o processo; o MongoDB preserva os
dados permanentes e as sessões CAPTCHA.

Os logs são JSON em stdout; nenhuma porta, arquivo de heartbeat ou volume
persistente local é necessário. Workers locais iniciam após carregar os Cogs
e sincronizar os comandos. Falhas críticas interrompem a inicialização. Se um
worker essencial terminar inesperadamente, o processo encerra com erro para
a PaaS reiniciá-lo. Desconexões temporárias do MongoDB são registradas e os
workers voltam a tentar; o driver e o gateway usam suas rotinas de reconexão.

## Memória e tarefas

| Estrutura | Limite/limpeza |
| --- | --- |
| Cache compartilhado | 4096 entradas; TTL padrão 60s; descarte LRU e limpeza periódica |
| Configuração/RBAC | TTL 60s e invalidação imediata nas alterações pelo bot |
| Janelas AutoMod | 10000 janelas, até 1000 eventos por janela; expiração e descarte LRU |
| Locks | até 4096 recursos simultâneos; liberados quando não há usuários/esperas |
| Fila local de auditoria | até 1000 IDs; lotes de 20; excedentes permanecem no MongoDB |
| EventBus emit | até 256 tarefas; eventos críticos usam publish aguardado |

A manutenção limpa cache/janelas a cada 20s. Cache também verifica TTL em cada
leitura. O controle de spam usa relógio monotônico e atualiza a janela sem
suspender a execução, somando e removendo pesos incrementalmente. IDs de
mensagem repetidos não aumentam a pontuação. Ao atingir o limite, limpa a
janela e ativa cooldown; as ações também têm cooldown por membro/regra.
Sob descarte LRU, uma janela transitória pode ser esquecida; esse é o limite
explícito de memória. Reiniciar o bot também reinicia pontuação e cooldown.

O cache evita consultas repetidas de configuração e permissões em cada
mensagem. Alterações externas feitas diretamente no MongoDB aparecem após o
TTL; alterações pelo painel e `/rbac` invalidam o cache imediatamente.

## Cases e consistência

Cases são intenções persistentes antes da ação externa. Estados:
`pending` → `applying` → `applied` → `completed`. Ações apenas no banco saltam
diretamente para completed. `failed` indica recusa conhecida; `uncertain`
indica resultado ambíguo de purge/kick. `active` e `revoked` descrevem a punição.
Timeouts expirados ou substituídos ficam inativos.

A numeração é atômica no MongoDB. IDs de interação Discord, de eventos AutoMod
e de reversões evitam duplicação ao repetir a mesma operação. Um novo comando
intencional tem outro ID. Locks asyncio serializam ações por alvo; intenções
pendentes impedem que uma ação nova ultrapasse uma recuperação incompleta.

Replica sets aplicam transações em projeções, outbox e conclusão. No standalone,
as mesmas etapas são idempotentes e recuperadas após falhas. Não existe uma
transação com a API do Discord. Bans verificam o estado atual; timeouts mantêm
o instante final original. Cases marcados como applied só concluem o banco.
Purge/kick interrompidos no ponto ambíguo ficam uncertain, sem repetir ações.

Para um case uncertain, confira `/case` e o audit log do Discord. Se confirmar
que a ação ocorreu, marque `status: applied` no case para concluir a persistência;
se confirmar que não ocorreu, marque pending para repetir. Casos incertos
bloqueiam novas ações no alvo até revisão. Não repita purge sem conferir o
que já foi apagado.

## Auditoria

O evento é persistido em `audit_outbox` antes de entrar na asyncio.Queue. A fila
só guarda IDs. Se estiver cheia, o registro continua no banco; o worker busca
pendências e recupera a fila após reinício. O EventBus é apenas desacoplamento
interno e não transporta dados entre processos.

O envio usa um marcador temporário de processamento no MongoDB para impedir
sobreposição e recuperar interrupções. Após crash durante envio, esse marcador
expira em até 120s. Cada tentativa tem timeout de 90s. Confirmação só é gravada
após sucesso. Backoff e cinco tentativas limitam falhas; registros mortos ficam
na outbox com `dead: true` e na coleção `audit_failures`.

A entrega é pelo menos uma vez: se o Discord receber e a confirmação MongoDB
falhar, pode haver duplicação com o mesmo ID no rodapé. Eventos sem canal
configurado recebem resultado explícito unconfigured.

Para reenviar após corrigir canal/permissões, redefina no registro da outbox:
`attempts: 0`, `dead: false`, `delivered: false`, `next_attempt: <agora UTC>` e
remova `lease_until`/`lease_token`. Preserve `_id`. A fila de falhas mantém o
histórico. Não há exclusão automática de cases/outbox; a retenção fica sob
controle do responsável pelo banco.

## CAPTCHA

As sessões ficam em `captcha_sessions`: hash da resposta, guild/user,
expiração, tentativas e estado consumido. Um índice TTL limpa sessões antigas;
a validade é conferida pelo horário mesmo antes dessa limpeza. Após cinco
respostas inválidas, é necessário gerar outro desafio.

A sessão é consumida após confirmar atribuição do cargo ou verificar que ele
já está presente. Se Discord funcionar e a gravação final falhar, a mesma
resposta permite concluir enquanto o desafio ainda estiver válido.

## Diagnóstico

| Sintoma | Conferir |
| --- | --- |
| Não inicia | variáveis, runtime Python, acesso ao MongoDB e criação de índices |
| Processo encerra ao carregar Cog | erro completo nos logs; não há inicialização parcial silenciosa |
| Comando ausente | escopo applications.commands e sincronização global |
| Não pune | permissões nativas/RBAC, hierarquia do autor/bot e case pendente |
| CAPTCHA não libera acesso | cargo válido, Manage Roles e permissões de canal do cargo |
| AutoMod não age | regra, exceções, admin/bot, janela/cooldown e permissões |
| Auditoria não chega | canal, Embed Links, outbox pending/dead, conectividade MongoDB |

A manutenção registra métricas por processo: cases concluídos, falhas de
callbacks/entrega, pendências e tamanho da fila. Esses contadores reiniciam
junto com o processo; não exigem dashboard ou coletor externo.

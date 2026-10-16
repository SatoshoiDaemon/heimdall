# Implementação do plano P0–P2

| Item | Implementação | Evidência automatizada |
| --- | --- | --- |
| P0-1 | Lista completa, página validada e botões sincronizados | 0/1/5/6/20 registros, páginas inválidas e navegação |
| P0-2 | Cargo configurável, sessão preservada, atribuição idempotente | código inválido/expirado/reusado, cargo ausente/elevado e falha Discord |
| P0-3 | Validador central de alvo/autor/bot, hierarquia também com RBAC | inferior/igual, admin, owner, bot, timeout e grant RBAC |
| P0-4 | Cases-intenção, estados, transações, IDs e reconciliação | falha de projeção, falha após Discord, reversão repetida, rollback Mongo real, bloqueio de reordenação |
| P0-5 | Outbox Mongo + stream/ack, leases, retries, DLQ e migração de fila | falha HTTP, entrega concorrente, retomada pending, perda Redis e migração real |
| P0-6 | Lua atômico, IDs únicos, cooldown, janela e falha explícita | concorrência ponderada, expiração real e Redis indisponível |
| P0-7 | Evento AutoMod com consumidor explícito e ModerationService | listener → evento → ação → case, ações individuais e regra desativada |
| P1-1 | Categorias, selects, modais, limites e permissão nos callbacks | guard de revogação; aceitação visual Discord na checklist de release |
| P1-2 | Spam, repetição, menções, palavras, URLs, convites e exceções | fronteiras de palavras, links, convites, exclusão de canal e ações |
| P1-3 | `/rbac` lista/grant/revoke/effective; apenas admin/dono edita | grants reais e hierarquia, consulta efetiva implementada |
| P1-4 | Filtros, páginas Mongo, origem e estados; expiração/supersessão | consultas filtradas, timeout novo inativa anterior, reversão repetida |
| P1-5 | Testes unitários + integração separada com Mongo/Redis reais | jobs independentes na CI |
| P1-6 | JSON, contexto, métricas/snapshot, heartbeat e Cog obrigatório | lint/compilação/imports; heartbeat de runtime na checklist de release |
| P2-1 | Imagem slim, UID 10001, healthcheck e Compose persistente | CI constrói imagem, valida Compose e usuário/imports |
| P2-2 | SCAN, cache versionado, RBAC sem cache de autorização, Lua | benchmark before/after gerado pela CI |
| P2-3 | Ruff ampliado/F401, formato, tipos progressivos, cobertura ≥65% | matriz Python 3.11/3.12/3.13 |
| P2-4 | Instalação, configuração, operação e contribuição | documentação versionada neste PR |
| P2-5 | 0.2.0rc1, changelog e critérios de publicação | checklist de aceitação; nenhuma tag estável antecipada |

A validação com Discord real e uma instalação com token real depende do
ambiente do mantenedor e está explicitamente pendente em `releasing.md`.
As integrações automatizadas usam bancos reais e um adaptador Discord simulado.

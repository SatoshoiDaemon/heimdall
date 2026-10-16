# Plano de correção e realinhamento — implementação

| Item | Resultado | Validação |
| --- | --- | --- |
| P0.1 | Cache/locks/spam locais; CAPTCHA e auditoria no MongoDB; dependência/cliente removidos | testes sem serviços auxiliares, limites e invalidação |
| P0.2 | Paginação única no banco para warnings/notes/history | vazio, 1/5/6/20/101, páginas inválidas e navegação |
| P0.3 | Cargo de verificado, expiração, cinco tentativas e recuperação | erros de código/cargo/atribuição/persistência e reuso |
| P0.4 | Validador autor/alvo/bot preserva hierarquia com RBAC | cargos inferiores/iguais, administrador, dono e concessões |
| P0.5 | Cases-intenção, contador atômico, IDs de operação, reversões e reconciliação | falhas Discord/Mongo, concorrência, rollback e reordenação |
| P0.6 | Persistência antes do envio, asyncio.Queue limitada e worker local | envio falha, fila cheia, reinício e retomada Mongo |
| P0.7 | Regras antigas preservadas; detecção aciona o mesmo serviço de moderação | evento → ação → case; regras desativadas e cooldown |
| P0.8 | Bootstrap obrigatório, workers supervisionados e fechamento idempotente | Mongo/Cog/sync falham; sucesso cancela workers e fecha conexão |
| P1.1 | Painel por categorias, selects/modais, entradas e callbacks validados | guard de permissão e checklist Discord real |
| P1.2 | Exceções, conteúdo, repetição e ações individuais | regras, exclusões, limites e detecção em memória |
| P1.3 | RBAC por usuário/cargo, permissões efetivas e auditoria | invalidação após concessão/revogação; hierarquia |
| P1.4 | Filtros e paginação uniformes, estados e respostas dentro dos limites | consultas, páginas e expiração/supersessão de timeouts |
| P1.5 | Unidade independente e integração com MongoDB configurado | matriz Python e MongoDB standalone/replica set |
| P1.6 | Estruturas limitadas, TTL, limpeza e tarefas limitadas | cache/janelas/locks/fila/backpressure, reconexão e recuperação |
| P2.1 | Distribuição por código-fonte e entrypoint Python | instalação limpa das dependências de produção |
| P2.2 | Somente Discord e MongoDB como serviços externos | requirements separados e import de produção |
| P2.3 | stdout, sinais, códigos de saída e ausência de portas/volumes | lifecycle automatizado e checklist de hospedagem |
| P2.4 | Instalação, deploy, configuração, dados persistentes/transitórios e diagnóstico | README e documentação complementares |
| P2.5 | 0.2.0rc2, changelog e critérios para 0.2.0 | aceitação real em PaaS/Discord ainda pendente |

O código automatizado é validado com adaptador Discord simulado e MongoDB real
na integração. Não se declara deploy ou aceitação num servidor Discord real
sem acesso ao ambiente de hospedagem do mantenedor.

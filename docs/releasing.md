# Preparação da release 0.2.0

A versão atual é `0.2.0rc1`. A tag estável só deve ser criada após concluir os
critérios abaixo. Criar arquivos de distribuição não equivale a validar uma
instalação conectada ao Discord.

## Critérios de aceitação

- [ ] CI verde em Python 3.11, 3.12 e 3.13, lint/formatação/tipos e cobertura ≥65%.
- [ ] Integração com MongoDB replica set e Redis reais aprovada.
- [ ] Imagem construída e execução sem root confirmada.
- [ ] Instalação limpa via Compose com volumes vazios e token de teste válido.
- [ ] Cogs e comandos carregados, intents e permissões configurados.
- [ ] Servidor de teste: 0/1/5/6/20 warnings, páginas inválidas e botões.
- [ ] Servidor de teste: CAPTCHA válido, inválido, expirado e role sem permissão.
- [ ] Servidor de teste: hierarquia do autor/bot, owner, admin e grants RBAC.
- [ ] Servidor de teste: cada regra AutoMod, exceções, cooldown e cases automáticos.
- [ ] Servidor de teste: ban/unban, timeout/reversão, purge e notas.
- [ ] Reinício com outbox pendente, falha de canal e reconciliação conferidos.
- [ ] Logs/healthcheck/backup de volumes e procedimento de recuperação conferidos.
- [ ] Changelog revisado e versão alterada para 0.2.0 em `src/version.py` e README.

## Publicação

1. Abra/revise o PR e aguarde todos os checks do commit final.
2. Conclua o teste de aceitação num servidor descartável; registre o resultado.
3. Faça merge, confira a CI de main e crie a tag `v0.2.0` nesse commit.
4. Publique release com CHANGELOG, mudanças de configuração e instruções de upgrade.

Nenhuma rotina cria a tag ou publica a release automaticamente. A operação com
token e servidor reais precisa de acesso ao ambiente do mantenedor.

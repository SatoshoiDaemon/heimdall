# Configuração e exemplos

## Painel

`/config` aceita Manage Server, Administrator, dono ou concessão RBAC `config`.
O painel expira em cinco minutos e pertence a quem o abriu. Cada interação e
cada submissão de modal revalida a autorização.

- **AutoMod**: configure regra, ação, limite, duração e cooldown no modal.
  Ação vazia desativa a regra. Há um modal separado para palavras/frases.
- **Verification**: selecione o cargo concedido após CAPTCHA. Deve ser um cargo
  comum de acesso, abaixo do bot, sem permissões elevadas ou gerenciadas.
- **Audit**: selecione um canal de texto que o bot possa acessar e escrever.
- **Exemptions**: selecione cargos e canais excluídos do AutoMod. Seleção vazia
  limpa a lista. Administradores e bots também são excluídos.
- **Permissions**: explica os comandos RBAC e a política de hierarquia.

A configuração é por servidor. Mudanças são validadas e auditadas e invalidam
imediatamente o cache local.

## Regras

| Nome | Detecção | Limite |
| --- | --- | --- |
| spam | soma de peso: 1 + 2 por menção | score acumulado |
| repeated | mesmo conteúdo, ignorando maiúsculas | mensagens na janela |
| mentions | menções a usuários + cargos ou everyone/here | menções na mensagem |
| words | palavras/frases bloqueadas, com fronteiras de palavra | não utilizado |
| urls | URL começando em http/https | não utilizado |
| invites | discord.gg ou discord.com/invite (inclui discordapp.com) | não utilizado |

Cada regra aceita `warn`, `delete` ou `timeout`; não há punições implícitas.
Duração do timeout: 1–2419200 segundos. Cooldown: 1–86400 segundos por membro e
regra, aplicado após sucesso. Limite: 1–1000. `spam_cooldown_seconds` é a janela
compartilhada de acumulação (padrão 60s); o cooldown de cada regra é independente.
Spam e repetição usam uma janela local em memória e limpam os registros ao atingir
o limite. Durante cooldown não repetem a punição.

As flags antigas `anti_spam_enabled`, `anti_link_enabled` e `anti_mention_enabled`
continuam como valores de compatibilidade. Uma entrada explícita em
`automod_rules` tem precedência sobre a flag antiga.

Exemplo: no modal escolha `spam`, `timeout`, limite `20`, duração `300` e
cooldown `60`. Para bloquear palavras, preencha o modal de palavras e habilite
a regra `words` com ação `delete`.

## Permissões

Somente o dono e administradores Discord podem usar `/rbac`, inclusive quando
há grants de `*`. RBAC não pode conceder a si próprio administração de grants.
Um administrador só pode alterar concessões de membros/cargos abaixo de si.

```text
/rbac operation:grant member:@Moderador permission:warn
/rbac operation:grant role:@Equipe permission:timeout
/rbac operation:revoke member:@Moderador permission:warn
/rbac operation:effective member:@Moderador
/rbac operation:list
```

A consulta efetiva combina grants do usuário, seus cargos e permissões nativas
e mostra os comandos liberados. As listagens têm navegação por páginas. Revogar um grant não remove permissões nativas nem
grants de outros cargos. `*` libera os comandos sujeitos a RBAC, respeitando
sempre a hierarquia.

## Moderação e consulta

```text
/warn target:@Membro reason:Spam
/warnings target:@Membro page:2
/timeout target:@Membro duration:30m reason:Flood
/unwarn case_number:12 reason:Advertência indevida
/history target:@Membro moderator:@Equipe action:WARN origin:automatic page:1
/history since:2026-10-01 until:2026-10-16
/case case_number:12
```

Datas ISO são interpretadas em UTC; `until` é um instante inclusivo. Use o dia
seguinte para incluir o último dia inteiro. A página começa em 1; páginas
inexistentes são rejeitadas. Os botões do histórico consultam o banco mantendo
os filtros. Advertências, notas e histórico consultam páginas diretamente no MongoDB,
sem recortar novamente uma página já carregada.

## Verificação

Configure o cargo antes de disponibilizar `/manual_verify`. O membro recebe
uma imagem efêmera e usa `/solve_captcha code:ABC123`. Código errado, expirado
ou consumido não concede cargo. Falhas de atribuição preservam o código até
sua expiração; se o cargo já foi concedido antes de uma interrupção, repetir a
solução conclui a sessão sem atribuí-lo novamente. Após cinco respostas inválidas,
gere outro desafio. A sessão permanece no MongoDB até expirar e continua
utilizável após reiniciar o processo.

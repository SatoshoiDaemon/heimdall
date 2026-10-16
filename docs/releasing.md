# Preparação da primeira release estável

A candidata atual é `0.2.0rc2`. A versão estável `0.2.0` depende da aceitação
automática e do uso real em hospedagem gerenciada e servidor Discord de teste.

## Aceitação automatizada

- [ ] CI verde no commit final, Python 3.11/3.12/3.13, Ruff/formatação/mypy.
- [ ] Cobertura ≥65% e testes de fluxo/concorrência aprovados.
- [ ] Integração com MongoDB standalone e replica set aprovada.
- [ ] Instalação limpa apenas com requirements.txt e imports de produção.
- [ ] Configuração inválida encerra com código 1; sinais encerram ordenadamente.

## Aceitação em PaaS e Discord

- [ ] Código-fonte completo enviado, runtime e variáveis configurados.
- [ ] Apenas instalação Python + python run.py necessários para iniciar.
- [ ] Conexão MongoDB, Cogs, workers e sincronização de comandos conferidos.
- [ ] /config funciona por categorias sem acesso manual ao banco.
- [ ] /warnings, /notes e /history: vazio, 1/5/6/20/101 registros, páginas e botões.
- [ ] CAPTCHA: válido, inválido, expirado, tentativas e falha de cargo.
- [ ] Hierarquia autor/bot, dono, administrador e RBAC conferidos.
- [ ] Moderação, reversões, AutoMod, exceções e cases automáticos conferidos.
- [ ] Reinício recupera sessões CAPTCHA, cases e auditoria pendente.
- [ ] Falha temporária MongoDB/Discord se recupera sem duplicar a operação.
- [ ] SIGTERM da plataforma conclui o encerramento e mantém pendências no banco.
- [ ] Changelog e versão estável atualizados em src/version.py e README.

Após concluir os critérios, faça merge, confira a CI de main e publique a tag
`v0.2.0` com changelog e instruções de atualização. Não crie a tag estável antes
da validação real; a candidata não equivale a um deploy testado em PaaS.

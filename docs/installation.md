# Instalação e deploy por código-fonte

## Hospedagem gerenciada

O deploy contém o repositório Python completo, especialmente `run.py`,
`requirements.txt` e `src/`. Não envie apenas o entrypoint ou um executável.

1. Selecione Python 3.11, 3.12 ou 3.13 na plataforma.
2. Envie o código-fonte mantendo os caminhos e diretórios.
3. Configure `BOT_TOKEN`, `MONGO_URI` e `MONGO_DB_NAME` no ambiente.
4. Configure a instalação: `python -m pip install -r requirements.txt`.
5. Configure a inicialização: `python run.py`.
6. Confira os logs de conexão, carregamento dos Cogs e sincronização dos comandos.

Se a plataforma instala `requirements.txt` automaticamente, basta configurar o
comando de inicialização. Os nomes dos campos variam por hospedagem. A plataforma
fornece runtime, gerenciamento do processo e rede; o Heimdall não precisa de
porta HTTP, volumes, acesso root ou serviços auxiliares.

## Variáveis

| Variável | Obrigatória | Valor/exemplo |
| --- | --- | --- |
| BOT_TOKEN | sim | token da aplicação Discord |
| MONGO_URI | sim | URI MongoDB acessível pela hospedagem |
| MONGO_DB_NAME | sim | `heimdall` |
| CAPTCHA_TIMEOUT_SECONDS | não | `300`; intervalo 1–86400 |
| LOG_WORKER_INTERVAL_SECONDS | não | `5`; intervalo 1–3600 |
| GUILD_ID | não | reservado; sincronização global continua sendo o padrão |

O ambiente tem precedência sobre `.env`. Token ausente, URI inválida ou erro
crítico de inicialização encerram o processo com código 1 e mensagem nos logs.
SIGTERM/SIGINT iniciam encerramento ordenado; o término normal retorna código 0.
Use a política de reinício da PaaS para falhas inesperadas.

MongoDB standalone é suportado. Replica sets permitem transações entre
coleções, mas não são requisito para iniciar: no standalone, a recuperação de
cases repara gravações parciais. Configure a URI/TLS e a autorização de rede
conforme seu provedor MongoDB. O usuário do banco deve poder ler/gravar as
coleções e criar índices.

## Discord

Habilite Server Members Intent e Message Content Intent no Developer Portal.
Use os escopos `bot` e `applications.commands` no convite. Conceda apenas os
recursos usados: View Channels, Send Messages, Embed Links, Attach Files,
Read Message History, Manage Messages, Ban Members, Kick Members,
Moderate Members e Manage Roles.

Coloque o cargo do bot acima dos alvos e do cargo de verificado. Permissões de
canal continuam valendo. Administrator não é necessário para o bot.
O administrador configura as funções usando `/config`, sem editar o banco.

## Desenvolvimento local

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python run.py
```

No Windows, ative com `.venv\Scripts\activate`. Para apenas executar,
instale `requirements.txt`. Não publique `.env` no repositório.

# Trilhas de mensagens semanais — protótipo

Protótipo que automatiza o envio semanal de mensagens a clientes de uma loja online,
de acordo com o perfil de compra de cada um. Dados da API pública
[DummyJSON](https://dummyjson.com); envio por WhatsApp **simulado** com a API da **Botmaker**.

- **Linguagem:** Python 3.12 · **Web:** FastAPI + templates Jinja2 (sem JavaScript) · **Banco:** SQLite
- **Diferenciais incluídos:** Dockerfile, testes no GitHub Actions e tratamento de erro quando a API não responde.

## Como rodar (Windows, `cmd`)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edite o `.env` (o token e o canal da Botmaker só são usados para **montar** a requisição simulada; nada é enviado). Depois:

```bat
python -m app.extract
python -m app.load
uvicorn app.main:app --reload
```

Abra <http://127.0.0.1:8000>.

| Comando | O que faz |
|---|---|
| `python -m app.extract` | Busca **todos** os clientes e carrinhos e grava o JSON bruto em `data/raw/AAAA-MM-DD/` |
| `python -m app.load` | Lê o JSON bruto mais recente e preenche a tabela `clientes` em `data/loja.db` |
| `uvicorn app.main:app --reload` | Sobe a aplicação web |

> Linux/macOS: troque `.venv\Scripts\activate` por `source .venv/bin/activate` e `copy` por `cp`.

## Docker

```bat
docker build -t trilhas-loja .
docker run --rm -v "%cd%\data:/app/data" trilhas-loja python -m app.extract
docker run --rm -v "%cd%\data:/app/data" trilhas-loja python -m app.load
docker run --rm -p 8000:8000 -v "%cd%\data:/app/data" --env-file .env trilhas-loja
```

O volume `-v` mantém banco e JSONs na sua pasta `data/` (a imagem não guarda dados). O `.env` nunca entra na imagem: as variáveis são passadas por `--env-file`.

## Testes

```bat
pip install -r requirements-dev.txt
python -m pytest -v
```

Os testes **não acessam a internet** (usam dados falsos e um servidor HTTP local) e usam banco temporário. O workflow `.github/workflows/tests.yml` roda a suíte a cada push/Pull Request e confere se a imagem Docker constrói.

## Variáveis de ambiente

| Variável | Obrigatória? | Descrição |
|---|---|---|
| `BOTMAKER_ACCESS_TOKEN` | para simular envios | Token da API (vai no cabeçalho `access-token`). Nunca é escrito no código nem gravado no banco |
| `BOTMAKER_CHANNEL_ID` | para simular envios | ID do canal de WhatsApp (`channelId`) |
| `BOTMAKER_CAMPAIGN` | não | Nome/ID da campanha (vazio = campanha padrão) |
| `DIA_SEMANA_ENVIO` | não (padrão `segunda`) | Dia da semana dos envios |
| `CODIGO_PAIS_PADRAO` | não (padrão `55`) | DDI para telefones sem código de país |
| `DB_PATH` / `RAW_DIR` | não | Caminhos do banco e dos JSONs brutos |

## Como cada item do enunciado foi atendido

| Item | Onde |
|---|---|
| Extração de todos os registros (paginação) | `app/api_client.py` (`limit` + `skip` até juntar `total`) |
| JSON bruto em `data/raw/AAAA-MM-DD/`, com data e hora no nome, sem sobrescrever | `app/extract.py` (arquivo aberto no modo `"x"`; colisão no mesmo segundo ganha sufixo `_1`, `_2`…) |
| Tabela de clientes (SQLite) | `app/db.py` + `app/load.py` |
| Trilhas, prioridade e motivo | `app/tracks.py` |
| Lista com filtro, página do cliente, confirmação/ajuste do analista gravada no banco | `app/main.py`, `app/templates/` |
| Cronograma (3 mensagens por trilha, 1 por semana, uma trilha por vez) | `app/schedule.py`, página `/cronograma` |
| Simulação de envio pela Botmaker, token por variável de ambiente | `app/whatsapp.py`, botão em `/cronograma`, histórico em `/historico` |

## Decisões de projeto

- **Valor total** = soma de `total` dos carrinhos (antes de descontos); **itens** = soma de `totalQuantity`. Cliente sem carrinho tem 0 e 0 (cai em *Incentivo*). O DummyJSON não informa moeda; seguindo o enunciado, os valores são exibidos em R$.
- **Estado** = `address.state`. **Sexo** é traduzido (`female` → feminino).
- **Trilhas sugeridas são calculadas na hora**, não gravadas. O banco guarda só a **decisão do analista**; recarregar os dados (`app.load`) usa UPSERT e nunca apaga decisões. O **filtro da lista** usa as trilhas *sugeridas*.
- **Só clientes confirmados** entram no cronograma. A trilha *Geral* só é sugerida quando nenhuma outra serve, mas o analista pode marcá-la manualmente.
- **Início do cronograma:** primeiro dia de envio configurado na data da confirmação **ou depois** (confirmou numa segunda e o dia é segunda → começa no mesmo dia). Ajustar as trilhas depois **não** muda a data inicial. As datas são sempre calculadas a partir da regra, não gravadas.
- **“Simular envios de hoje”** simula só as mensagens com data de hoje (não reenvia dias passados) e é **idempotente**: clicar duas vezes não duplica o histórico.
- **Telefone:** só dígitos, com código do país (`+81 965-431-3024` → `819654313024`). Sem `+` nem `00`, assume o DDI padrão.

## Botmaker: requisição montada

Segui a documentação “Como enviar notificações por meio da API?” da Botmaker (API v2.0):

```
POST https://api.botmaker.com/v2.0/notifications
access-token: <BOTMAKER_ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json

{
  "name": "Trilha Alto valor - mensagem 1 - 2026-10-26",
  "channelId": "<BOTMAKER_CHANNEL_ID>",
  "campaign": null,
  "intentIdOrName": "trilha_alto_valor_msg_1",
  "contacts": [{
    "contactId": "819654313024",
    "variables": {"nome": "Emily", "mensagem": "Olá, Emily! …"},
    "webhookPayload": "cliente-7|alto_valor|msg-1|2026-10-26"
  }]
}
```

Escolhi `/notifications` porque a própria documentação diz que, **fora da janela de 24 h** da última mensagem do cliente, o WhatsApp exige templates aprovados — e mensagens semanais de marketing estão sempre fora dela. Em produção, os 15 templates/intents (`trilha_<trilha>_msg_<n>`) precisariam existir na Botmaker. No histórico, o token aparece como `<BOTMAKER_ACCESS_TOKEN>`.

## Tratamento de erro quando a API não responde

- Timeout de 10 s em toda requisição.
- Falhas temporárias (erro de rede, timeout, HTTP 429/500/502/503/504) → até 3 tentativas com espera crescente (1 s, 2 s).
- Erros definitivos (ex.: 404), JSON inválido ou dados incompletos → falha imediata com mensagem clara.
- A extração só grava arquivos **depois** de buscar users **e** carts: se um falhar, nada fica gravado pela metade. O script termina com código de saída 1.

## Estrutura

```
app/
  api_client.py   cliente DummyJSON (paginação, timeout, retentativas)
  extract.py      grava o JSON bruto
  load.py         monta a tabela de clientes
  tracks.py       regras das trilhas e motivos
  messages.py     textos das mensagens e substituição de {nome}
  schedule.py     cálculo do cronograma
  whatsapp.py     requisição simulada da Botmaker
  db.py           conexão e esquema do SQLite
  repositorio.py  consultas SQL
  config.py       variáveis de ambiente
  main.py         rotas FastAPI
  templates/      páginas HTML
tests/            testes automatizados
```

## Limitações conhecidas / próximos passos

- Não há como **desfazer** uma confirmação (só ajustar as trilhas).
- Não há login: a decisão grava a data, mas não *quem* decidiu.
- Datas usam o fuso do servidor (sem fuso configurável).
- A lista de clientes não é paginada (são ~200 clientes).
- O envio é só simulado; o envio real exigiria tratar 429, falhas por contato e o webhook de status.
- Os dados só são atualizados por linha de comando (`extract` + `load`), não pela interface.

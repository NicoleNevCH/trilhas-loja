# Trilhas de mensagens semanais

Protótipo do teste técnico de Desenvolvedor(a) Júnior. Ele busca clientes e carrinhos na API do DummyJSON, sugere uma ou mais trilhas de mensagem para cada cliente, deixa um analista confirmar e monta o cronograma semanal. O envio por WhatsApp (Botmaker) é só simulado.

Feito com Python, FastAPI, SQLite e Docker.

## Como rodar

No cmd do Windows, dentro da pasta do projeto:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
python -m app.extract
python -m app.load
uvicorn app.main:app --reload
```

Depois é só abrir http://127.0.0.1:8000. (No Linux/macOS, troque o `activate` por `source .venv/bin/activate` e o `copy` por `cp`.)

Com Docker:

```bat
docker build -t trilhas-loja .
docker run --rm -v "%cd%\data:/app/data" trilhas-loja python -m app.extract
docker run --rm -v "%cd%\data:/app/data" trilhas-loja python -m app.load
docker run --rm -p 8000:8000 -v "%cd%\data:/app/data" --env-file .env trilhas-loja
```

O `-v` deixa o banco e os JSONs na sua pasta `data/`, fora da imagem.

Os testes rodam com `python -m pytest`. Eles não usam a internet e também rodam no GitHub Actions a cada push.

## Variáveis de ambiente

Ficam no arquivo `.env` (o `.env.example` é o modelo, e o `.env` não vai para o Git):

- `BOTMAKER_ACCESS_TOKEN`: token da API da Botmaker. Só serve para montar a requisição simulada. Não fica no código nem no banco.
- `BOTMAKER_CHANNEL_ID`: id do canal de WhatsApp.
- `DIA_SEMANA_ENVIO`: dia da semana dos envios (segunda, terça...). O padrão é segunda.

## Como usar

1. Em **Clientes**, abra um cliente, veja as trilhas sugeridas com o motivo e confirme ou ajuste.
2. Em **Cronograma** aparecem os envios das próximas semanas, só dos clientes confirmados.
3. **Simular envios de hoje** grava no **Histórico** a requisição que seria enviada.

O botão só simula o que está previsto para hoje. Para testar, coloque em `DIA_SEMANA_ENVIO` o dia da semana de hoje.

## Decisões que tomei

- Valor total do cliente é a soma do `total` dos carrinhos (antes de descontos), e itens é a soma do `totalQuantity`. Quem não tem carrinho fica com 0. O DummyJSON não informa moeda, então mostro em R$ como no enunciado.
- As trilhas sugeridas são calculadas na hora e não ficam no banco. O banco guarda só a decisão do analista, então recarregar os dados não apaga nada. O filtro da lista usa as trilhas sugeridas.
- A trilha Geral só é sugerida quando nenhuma outra serve, mas o analista pode marcá-la na mão.
- O primeiro envio é no dia da semana configurado, na data da confirmação ou depois. Ajustar as trilhas depois não muda essa data. As datas são sempre calculadas, não gravadas.
- O botão não duplica: clicar duas vezes não repete o histórico.
- O telefone vai só com dígitos e com o código do país (`+81 965-431-3024` vira `819654313024`).

## Botmaker

Segui o artigo da Botmaker sobre envio de notificações pela API:

- `POST https://api.botmaker.com/v2.0/notifications`
- cabeçalhos `access-token`, `Content-Type` e `Accept`
- corpo com `name`, `channelId`, `intentIdOrName` e `contacts` (`contactId`, `variables` e `webhookPayload`)

Usei esse endpoint porque o WhatsApp só aceita texto livre até 24 h depois da última mensagem do cliente. Mensagem semanal de marketing precisa de template aprovado. Em produção, os templates `trilha_<trilha>_msg_<n>` teriam que existir na Botmaker. No histórico, o token aparece como `<BOTMAKER_ACCESS_TOKEN>`.

## Quando a API cai

- Toda chamada tem timeout de 10 s.
- Erro de rede ou HTTP 5xx: até 3 tentativas, esperando 1 s e depois 2 s.
- Erro 4xx, JSON inválido ou dados incompletos: falha na hora, com mensagem clara.
- A extração só grava os arquivos depois de buscar clientes e carrinhos. Se um falhar, nada fica gravado pela metade.

## O que ficou de fora

- Não dá para desfazer uma confirmação, só ajustar as trilhas.
- Não há login, então a decisão não guarda quem confirmou.
- As datas usam o fuso do servidor.
- A lista de clientes não tem paginação (são uns 200).
- O envio é só simulado. O real teria que tratar falhas por contato e o webhook de status.
- Os dados só são atualizados pela linha de comando (`extract` e `load`).


"""
Protótipo de mensagens semanais por trilhas para clientes de uma loja online.

Visão geral do fluxo (cada etapa é um módulo):

    api_client.py  -> busca clientes e carrinhos na API pública DummyJSON
    extract.py     -> grava o JSON bruto em data/raw/AAAA-MM-DD/ (nunca sobrescreve)
    load.py        -> lê o JSON bruto mais recente e monta a tabela `clientes` (SQLite)
    tracks.py      -> regras das trilhas e o motivo de cada sugestão
    schedule.py    -> cronograma: 3 mensagens por trilha, 1 por semana
    whatsapp.py    -> monta (sem enviar) a requisição da API da Botmaker
    main.py        -> aplicação web (FastAPI) que junta tudo
"""

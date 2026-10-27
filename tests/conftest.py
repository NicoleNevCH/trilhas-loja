"""
Fixtures (preparações) compartilhadas pelos testes.

Uma "fixture" do pytest é uma função que prepara algo antes do teste e entrega o
resultado como argumento. Com `autouse=True` ela roda antes de TODO teste.
"""
import pytest


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    """Isola cada teste: banco e pasta raw temporários + variáveis de ambiente fixas.

    - `tmp_path`: pasta temporária única por teste (o pytest apaga depois).
    - `monkeypatch`: troca variáveis de ambiente só durante o teste e desfaz ao final.
    Resultado: os testes nunca tocam no seu data/loja.db real, nem no seu .env.
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "teste.db"))
    monkeypatch.setenv("RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("DIA_SEMANA_ENVIO", "segunda")
    monkeypatch.setenv("BOTMAKER_ACCESS_TOKEN", "token-falso-de-teste")
    monkeypatch.setenv("BOTMAKER_CHANNEL_ID", "botproject-whatsapp-5511947038000")
    monkeypatch.delenv("BOTMAKER_CAMPAIGN", raising=False)
    monkeypatch.delenv("CODIGO_PAIS_PADRAO", raising=False)


# Dados de exemplo no formato do DummyJSON (só os campos que usamos).
USUARIOS = [
    {"id": 1, "firstName": "Emily", "lastName": "Johnson", "age": 28, "gender": "female",
     "phone": "+81 965-431-3024", "address": {"state": "Mississippi"}},
    {"id": 2, "firstName": "Michael", "lastName": "Williams", "age": 35, "gender": "male",
     "phone": "+49 614-958-9364", "address": {"state": "Ohio"}},
    {"id": 3, "firstName": "Sophia", "lastName": "Brown", "age": 45, "gender": "female",
     "phone": "+61 770-727-4137", "address": {"state": "Texas"}},
]

CARRINHOS = [
    # Emily: dois carrinhos -> 12.450,00 e 20 itens
    {"id": 1, "userId": 1, "total": 10000.50, "totalQuantity": 12},
    {"id": 2, "userId": 1, "total": 2449.50, "totalQuantity": 8},
    # Michael: um carrinho pequeno -> 500,00 e 3 itens
    {"id": 3, "userId": 2, "total": 500.00, "totalQuantity": 3},
    # Sophia: nenhum carrinho
]


@pytest.fixture
def usuarios():
    return [dict(u) for u in USUARIOS]


@pytest.fixture
def carrinhos():
    return [dict(c) for c in CARRINHOS]

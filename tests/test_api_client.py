"""
Testes do cliente da API (api_client.py): paginação, retentativas e erros.

Duas estratégias:
  1. Sessão FALSA (rápidas): simulam respostas e falhas específicas.
  2. Servidor HTTP LOCAL de verdade (1 teste): garante que o código com `requests`
     reais funciona de ponta a ponta, sem depender da internet.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from app.api_client import ApiResponseError, ApiUnavailableError, DummyJsonClient


class RespostaFalsa:
    def __init__(self, status=200, dados=None, json_invalido=False):
        self.status_code = status
        self._dados = dados
        self._json_invalido = json_invalido

    def json(self):
        if self._json_invalido:
            raise ValueError("JSON inválido")
        return self._dados


class SessaoFalsa:
    """Devolve, em ordem, as respostas (ou levanta as exceções) que recebeu."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append({"url": url, "params": dict(params), "timeout": timeout})
        item = self.respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def pagina(chave, ids, total):
    return RespostaFalsa(200, {chave: [{"id": i} for i in ids], "total": total})


def cliente_com(respostas, **kwargs):
    esperas = []
    sessao = SessaoFalsa(respostas)
    cliente = DummyJsonClient(sessao=sessao, dormir=esperas.append, tamanho_pagina=2, **kwargs)
    return cliente, sessao, esperas


def test_busca_todas_as_paginas():
    cliente, sessao, _ = cliente_com([
        pagina("users", [1, 2], 5), pagina("users", [3, 4], 5), pagina("users", [5], 5),
    ])
    resultado = cliente.buscar_todos("users")
    assert [u["id"] for u in resultado["users"]] == [1, 2, 3, 4, 5]
    assert resultado["total"] == 5
    # `skip` avança de acordo com o que já foi recebido; `limit` é o tamanho da página.
    assert [c["params"] for c in sessao.chamadas] == [
        {"limit": 2, "skip": 0}, {"limit": 2, "skip": 2}, {"limit": 2, "skip": 4},
    ]
    assert all(c["timeout"] for c in sessao.chamadas)  # nunca sem timeout


def test_tenta_de_novo_apos_erro_5xx_e_usa_espera_crescente():
    cliente, sessao, esperas = cliente_com([
        RespostaFalsa(503), RespostaFalsa(500), pagina("carts", [1], 1),
    ], tentativas=3)
    assert cliente.buscar_todos("carts")["total"] == 1
    assert len(sessao.chamadas) == 3
    assert esperas == [1.0, 2.0]  # backoff: 1s, depois 2s


def test_tenta_de_novo_apos_falha_de_rede():
    cliente, _, esperas = cliente_com([
        requests.exceptions.ConnectionError("sem rede"),
        requests.exceptions.Timeout("lento"),
        pagina("users", [1], 1),
    ], tentativas=3)
    assert cliente.buscar_todos("users")["total"] == 1
    assert len(esperas) == 2


def test_desiste_depois_de_todas_as_tentativas():
    cliente, sessao, esperas = cliente_com(
        [requests.exceptions.ConnectionError("fora do ar")] * 3, tentativas=3
    )
    with pytest.raises(ApiUnavailableError) as erro:
        cliente.buscar_todos("users")
    assert "3 tentativas" in str(erro.value)
    assert len(sessao.chamadas) == 3
    assert len(esperas) == 2  # não espera depois da última tentativa


def test_erro_4xx_nao_tenta_de_novo():
    cliente, sessao, esperas = cliente_com([RespostaFalsa(404)])
    with pytest.raises(ApiResponseError):
        cliente.buscar_todos("users")
    assert len(sessao.chamadas) == 1 and esperas == []


def test_json_invalido():
    cliente, _, _ = cliente_com([RespostaFalsa(200, json_invalido=True)])
    with pytest.raises(ApiResponseError):
        cliente.buscar_todos("users")


def test_formato_inesperado():
    cliente, _, _ = cliente_com([RespostaFalsa(200, {"outra_chave": []})])
    with pytest.raises(ApiResponseError):
        cliente.buscar_todos("users")


def test_dados_incompletos_sao_rejeitados():
    # A API diz que há 5 registros, mas a segunda página vem vazia.
    cliente, _, _ = cliente_com([pagina("users", [1, 2], 5), pagina("users", [], 5)])
    with pytest.raises(ApiResponseError) as erro:
        cliente.buscar_todos("users")
    assert "incompletos" in str(erro.value)


# ----------------------------------------------------------- servidor local real
class ManipuladorFalso(BaseHTTPRequestHandler):
    """Imita a paginação do DummyJSON: 5 usuários; as 1ªs `falhas` chamadas dão 503."""

    falhas_restantes = 0

    def do_GET(self):
        if type(self).falhas_restantes > 0:
            type(self).falhas_restantes -= 1
            self.send_response(503)
            self.end_headers()
            return
        consulta = parse_qs(urlparse(self.path).query)
        limite = int(consulta.get("limit", ["30"])[0])
        pular = int(consulta.get("skip", ["0"])[0])
        todos = [{"id": i} for i in range(1, 6)]
        corpo = json.dumps({
            "users": todos[pular:pular + limite], "total": 5, "skip": pular, "limit": limite,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):  # silencia o log de cada requisição
        pass


@pytest.fixture
def servidor_local():
    ManipuladorFalso.falhas_restantes = 0
    servidor = HTTPServer(("127.0.0.1", 0), ManipuladorFalso)  # porta 0 = o SO escolhe uma livre
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}"
    servidor.shutdown()


def test_http_real_com_paginacao_e_recuperacao_de_falha(servidor_local):
    ManipuladorFalso.falhas_restantes = 1  # a 1ª chamada falha com 503 e depois funciona
    cliente = DummyJsonClient(url_base=servidor_local, tamanho_pagina=2, espera_inicial=0)
    resultado = cliente.buscar_todos("users")
    assert [u["id"] for u in resultado["users"]] == [1, 2, 3, 4, 5]


def test_http_real_servidor_fora_do_ar():
    # Porta 9 (discard) em localhost não tem ninguém escutando -> conexão recusada.
    cliente = DummyJsonClient(url_base="http://127.0.0.1:9", tentativas=2, espera_inicial=0, timeout=1)
    with pytest.raises(ApiUnavailableError):
        cliente.buscar_todos("users")

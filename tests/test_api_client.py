"""Testes da busca na API: paginação, tentativas e erros (sem usar a internet)."""
import pytest
import requests

from app import api_client
from app.api_client import ApiError, buscar_todos


class Resposta:
    """Resposta falsa, parecida com a do requests."""

    def __init__(self, status=200, dados=None):
        self.status_code = status
        self._dados = dados

    def json(self):
        if self._dados is None:
            raise ValueError("sem JSON")
        return self._dados


def pagina(recurso, ids, total):
    return Resposta(200, {recurso: [{"id": i} for i in ids], "total": total})


@pytest.fixture
def api(monkeypatch):
    """Troca requests.get e time.sleep por versões falsas.

    Devolve uma função: api(resposta1, resposta2, ...) define o que cada chamada
    devolve (se for uma exceção, ela é levantada). O resultado traz os parâmetros
    usados em cada chamada e as esperas pedidas.
    """
    def configurar(*respostas):
        fila = list(respostas)
        chamadas, esperas = [], []

        def get_falso(url, params=None, timeout=None):
            chamadas.append(params)
            item = fila.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        monkeypatch.setattr(api_client.requests, "get", get_falso)
        monkeypatch.setattr(api_client.time, "sleep", esperas.append)
        monkeypatch.setattr(api_client, "TAMANHO_PAGINA", 2)
        return chamadas, esperas

    return configurar


def test_busca_todas_as_paginas(api):
    chamadas, _ = api(pagina("users", [1, 2], 5), pagina("users", [3, 4], 5), pagina("users", [5], 5))
    resultado = buscar_todos("users")
    assert [u["id"] for u in resultado["users"]] == [1, 2, 3, 4, 5]
    assert resultado["total"] == 5
    assert chamadas == [{"limit": 2, "skip": 0}, {"limit": 2, "skip": 2}, {"limit": 2, "skip": 4}]


def test_tenta_de_novo_quando_o_servidor_falha(api):
    chamadas, esperas = api(Resposta(503), Resposta(500), pagina("carts", [1], 1))
    assert buscar_todos("carts")["total"] == 1
    assert len(chamadas) == 3
    assert esperas == [1, 2]   # espera cada vez mais


def test_tenta_de_novo_quando_a_rede_falha(api):
    _, esperas = api(requests.exceptions.ConnectionError(), requests.exceptions.Timeout(),
                     pagina("users", [1], 1))
    assert buscar_todos("users")["total"] == 1
    assert len(esperas) == 2


def test_desiste_depois_de_3_tentativas(api):
    chamadas, esperas = api(*[requests.exceptions.ConnectionError()] * 3)
    with pytest.raises(ApiError) as erro:
        buscar_todos("users")
    assert "3 tentativas" in str(erro.value)
    assert len(chamadas) == 3 and len(esperas) == 2   # não espera depois da última


def test_erro_404_nao_tenta_de_novo(api):
    chamadas, _ = api(Resposta(404))
    with pytest.raises(ApiError):
        buscar_todos("users")
    assert len(chamadas) == 1


def test_json_invalido(api):
    api(Resposta(200, None))
    with pytest.raises(ApiError):
        buscar_todos("users")


def test_formato_inesperado(api):
    api(Resposta(200, {"outra_coisa": []}))
    with pytest.raises(ApiError):
        buscar_todos("users")


def test_dados_incompletos(api):
    # a API diz que tem 5, mas a segunda página vem vazia
    api(pagina("users", [1, 2], 5), pagina("users", [], 5))
    with pytest.raises(ApiError) as erro:
        buscar_todos("users")
    assert "incompletos" in str(erro.value)
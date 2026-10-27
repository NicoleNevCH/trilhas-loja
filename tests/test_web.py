"""
Testes de ponta a ponta da aplicação web (main.py) com o TestClient do FastAPI.

O TestClient chama o app diretamente (sem abrir porta de rede) e devolve as respostas
HTML, então testamos o fluxo real: lista -> filtro -> confirmar -> cronograma ->
simular envios -> histórico.
"""
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import load, main, repositorio
from app.db import conectar

# 2026-10-26 é uma SEGUNDA-feira (dia de envio configurado nos testes).
HOJE = datetime(2026, 10, 26, 10, 0, 0)


@pytest.fixture
def cliente_http(monkeypatch, usuarios, carrinhos):
    monkeypatch.setattr(main, "agora", lambda: HOJE)  # congela "hoje"
    with conectar() as conn:
        repositorio.upsert_clientes(conn, load.montar_clientes(usuarios, carrinhos))
    return TestClient(main.app)


def confirmar(http, cid, trilhas):
    return http.post(f"/clientes/{cid}/confirmar", data={"trilhas": trilhas}, follow_redirects=False)


def test_raiz_redireciona_para_clientes(cliente_http):
    resposta = cliente_http.get("/", follow_redirects=False)
    assert resposta.status_code in (302, 307)
    assert resposta.headers["location"] == "/clientes"


def test_lista_mostra_clientes_e_trilhas_sugeridas(cliente_http):
    html = cliente_http.get("/clientes").text
    assert "Emily Johnson" in html and "Michael Williams" in html and "Sophia Brown" in html
    assert "R$ 12.450,00" in html


def test_filtro_por_trilha(cliente_http):
    html = cliente_http.get("/clientes", params={"trilha": "Alto valor"}).text
    assert "Emily Johnson" in html          # 12.450 >= 10.000
    assert "Michael Williams" not in html
    assert "Sophia Brown" not in html

    html = cliente_http.get("/clientes", params={"trilha": "Incentivo"}).text
    assert "Michael Williams" in html and "Sophia Brown" in html   # < 1.000 (Sophia: 0)
    assert "Emily Johnson" not in html


def test_filtro_com_trilha_invalida(cliente_http):
    assert cliente_http.get("/clientes", params={"trilha": "Inventada"}).status_code == 400


def test_lista_vazia_orienta_a_carregar_os_dados(monkeypatch):
    # Sem a fixture de clientes: banco vazio.
    html = TestClient(main.app).get("/clientes").text
    assert "python -m app.load" in html


def test_pagina_do_cliente_mostra_motivos(cliente_http):
    html = cliente_http.get("/clientes/1").text
    assert "valor total R$ 12.450,00 ≥ R$ 10.000,00" in html
    assert "20 itens ≥ 15 itens" in html
    assert "idade 28 &lt; 30 anos" in html          # "<" aparece escapado no HTML
    assert "Ainda não confirmado" in html


def test_cliente_inexistente_da_404(cliente_http):
    assert cliente_http.get("/clientes/999").status_code == 404
    assert confirmar(cliente_http, 999, ["Geral"]).status_code == 404


def test_confirmar_grava_no_banco_e_redireciona(cliente_http):
    resposta = confirmar(cliente_http, 1, ["Público jovem", "Alto valor"])
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/clientes/1?salvo=1"

    with conectar() as conn:
        data, trilhas = repositorio.buscar_confirmacao(conn, 1)
    assert str(data) == "2026-10-26"
    assert trilhas == ["Alto valor", "Público jovem"]   # gravadas em ordem de prioridade

    html = cliente_http.get("/clientes/1?salvo=1").text
    assert "Decisão gravada" in html and "Confirmado em 26/10/2026" in html


def test_analista_pode_ajustar_trilhas(cliente_http):
    confirmar(cliente_http, 1, ["Alto valor", "Compra em quantidade", "Público jovem"])
    confirmar(cliente_http, 1, ["Geral"])          # ajuste: troca tudo por "Geral"
    with conectar() as conn:
        assert repositorio.buscar_confirmacao(conn, 1)[1] == ["Geral"]


def test_confirmar_sem_nenhuma_trilha_e_rejeitado(cliente_http):
    resposta = cliente_http.post("/clientes/1/confirmar", data={})
    assert resposta.status_code == 400
    assert "Marque pelo menos uma trilha" in resposta.text
    with conectar() as conn:
        assert repositorio.buscar_confirmacao(conn, 1) is None


def test_confirmar_com_trilha_invalida_e_rejeitado(cliente_http):
    resposta = cliente_http.post("/clientes/1/confirmar", data={"trilhas": ["Falsa"]})
    assert resposta.status_code == 400
    with conectar() as conn:
        assert repositorio.buscar_confirmacao(conn, 1) is None


def test_so_confirmados_entram_no_cronograma(cliente_http):
    html = cliente_http.get("/cronograma").text
    assert "Nenhum cliente confirmado ainda" in html

    confirmar(cliente_http, 1, ["Alto valor"])      # só a Emily
    html = cliente_http.get("/cronograma").text
    assert "Emily" in html
    assert "Michael" not in html and "Sophia" not in html
    assert "26/10/2026" in html and "02/11/2026" in html and "09/11/2026" in html


def test_cronograma_respeita_numero_de_semanas(cliente_http):
    confirmar(cliente_http, 1, ["Alto valor"])
    um = cliente_http.get("/cronograma", params={"semanas": 1}).text
    assert "26/10/2026" in um and "02/11/2026" not in um
    assert cliente_http.get("/cronograma", params={"semanas": 0}).status_code == 422


def test_simular_envios_de_hoje_grava_historico_sem_token(cliente_http):
    confirmar(cliente_http, 1, ["Alto valor"])
    confirmar(cliente_http, 2, ["Incentivo"])
    resposta = cliente_http.post("/simular-envios", follow_redirects=False)
    assert resposta.status_code == 303
    assert "novos=2" in resposta.headers["location"]

    with conectar() as conn:
        linhas = repositorio.listar_historico(conn)
    assert len(linhas) == 2   # só as mensagens de HOJE (1ª de cada cliente)
    emily = next(l for l in linhas if l["cliente_id"] == 1)
    assert emily["mensagem"].startswith("Olá, Emily!")
    assert emily["data_prevista"] == "2026-10-26"

    req = json.loads(emily["requisicao_json"])
    assert req["metodo"] == "POST"
    assert req["url"] == "https://api.botmaker.com/v2.0/notifications"
    assert req["corpo"]["contacts"][0]["contactId"] == "819654313024"
    assert "token-falso-de-teste" not in emily["requisicao_json"]   # token não é gravado

    html = cliente_http.get("/historico").text
    assert "Emily Johnson" in html and "Ver requisição" in html


def test_simular_duas_vezes_nao_duplica(cliente_http):
    confirmar(cliente_http, 1, ["Alto valor"])
    cliente_http.post("/simular-envios")
    segunda = cliente_http.post("/simular-envios", follow_redirects=False)
    assert "novos=0" in segunda.headers["location"] and "repetidos=1" in segunda.headers["location"]
    with conectar() as conn:
        assert len(repositorio.listar_historico(conn)) == 1
    assert "Simulado" in cliente_http.get("/cronograma").text


def test_simular_sem_envios_hoje(cliente_http):
    # Ninguém confirmado -> nada previsto; não deve dar erro.
    resposta = cliente_http.post("/simular-envios", follow_redirects=False)
    assert resposta.status_code == 303 and "previstos=0" in resposta.headers["location"]


def test_simular_sem_token_mostra_erro_claro_e_nao_grava(cliente_http, monkeypatch):
    confirmar(cliente_http, 1, ["Alto valor"])
    monkeypatch.delenv("BOTMAKER_ACCESS_TOKEN")
    resposta = cliente_http.post("/simular-envios")
    assert resposta.status_code == 500
    assert "BOTMAKER_ACCESS_TOKEN" in resposta.text
    with conectar() as conn:
        assert repositorio.listar_historico(conn) == []


def test_telefone_invalido_nao_impede_os_demais(cliente_http):
    confirmar(cliente_http, 1, ["Alto valor"])
    confirmar(cliente_http, 2, ["Incentivo"])
    with conectar() as conn:
        conn.execute("UPDATE clientes SET telefone = 'sem telefone' WHERE id = 1")
    resposta = cliente_http.post("/simular-envios", follow_redirects=False)
    assert "novos=1" in resposta.headers["location"] and "falhas=1" in resposta.headers["location"]


def test_historico_vazio(cliente_http):
    assert "Ainda não há envios simulados" in cliente_http.get("/historico").text

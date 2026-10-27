"""Testes da requisição simulada da Botmaker (whatsapp.py)."""
import json
from datetime import date

import pytest

from app.config import ConfigError
from app.schedule import Envio
from app.whatsapp import (
    TOKEN_OCULTO, URL_BOTMAKER, montar_requisicao, normalizar_telefone, slug,
)


def envio(**sobrescrever):
    dados = dict(
        data=date(2026, 10, 26), cliente_id=7, cliente_nome="Emily Johnson",
        telefone="+81 965-431-3024", trilha="Alto valor", numero_mensagem=1,
        texto="Olá, Emily! Você é um dos nossos clientes especiais.",
    )
    dados.update(sobrescrever)
    return Envio(**dados)


@pytest.mark.parametrize("entrada, esperado", [
    ("+81 965-431-3024", "819654313024"),        # com "+" o código do país já está presente
    ("+55 (11) 95566-7788", "5511955667788"),
    ("0055 11 95566-7788", "5511955667788"),     # prefixo internacional 00
    ("(11) 95566-7788", "5511955667788"),        # sem DDI -> assume 55
    ("011 95566-7788", "5511955667788"),         # "0" de tronco é descartado
])
def test_normalizar_telefone(entrada, esperado):
    assert normalizar_telefone(entrada) == esperado


def test_ddi_padrao_configuravel(monkeypatch):
    monkeypatch.setenv("CODIGO_PAIS_PADRAO", "351")
    assert normalizar_telefone("912 345 678") == "351912345678"


def test_telefone_sem_digitos_e_invalido():
    with pytest.raises(ValueError):
        normalizar_telefone("sem telefone")


def test_slug():
    assert slug("Público jovem") == "publico_jovem"
    assert slug("Compra em quantidade") == "compra_em_quantidade"


def test_formato_da_requisicao_conforme_a_documentacao():
    req = montar_requisicao(envio())

    assert req.metodo == "POST"
    assert req.url == URL_BOTMAKER == "https://api.botmaker.com/v2.0/notifications"
    assert req.cabecalhos == {
        "access-token": "token-falso-de-teste",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    corpo = req.corpo
    assert corpo["channelId"] == "botproject-whatsapp-5511947038000"
    assert corpo["campaign"] is None                       # null = campanha padrão
    assert corpo["name"] == "Trilha Alto valor - mensagem 1 - 2026-10-26"
    assert corpo["intentIdOrName"] == "trilha_alto_valor_msg_1"
    (contato,) = corpo["contacts"]
    assert contato["contactId"] == "819654313024"          # só dígitos, com código do país
    assert contato["variables"]["nome"] == "Emily"         # primeiro nome
    assert contato["variables"]["mensagem"].startswith("Olá, Emily!")
    assert contato["webhookPayload"] == "cliente-7|alto_valor|msg-1|2026-10-26"


def test_campanha_opcional_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("BOTMAKER_CAMPAIGN", "trilhas-semanais")
    assert montar_requisicao(envio()).corpo["campaign"] == "trilhas-semanais"


def test_token_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("BOTMAKER_ACCESS_TOKEN", "outro-token")
    assert montar_requisicao(envio()).cabecalhos["access-token"] == "outro-token"


@pytest.mark.parametrize("variavel", ["BOTMAKER_ACCESS_TOKEN", "BOTMAKER_CHANNEL_ID"])
def test_sem_variavel_obrigatoria_falha_com_mensagem_clara(monkeypatch, variavel):
    monkeypatch.delenv(variavel)
    with pytest.raises(ConfigError) as erro:
        montar_requisicao(envio())
    assert variavel in str(erro.value)


def test_token_nunca_vai_para_o_registro():
    registro = montar_requisicao(envio()).para_registro()
    assert registro["cabecalhos"]["access-token"] == TOKEN_OCULTO
    assert "token-falso-de-teste" not in montar_requisicao(envio()).para_json()
    assert json.loads(montar_requisicao(envio()).para_json())["metodo"] == "POST"


def test_repr_nao_vaza_o_token():
    assert "token-falso-de-teste" not in repr(montar_requisicao(envio()))


def test_token_nao_esta_escrito_no_codigo():
    """Garantia extra: o valor do token de teste não existe em nenhum arquivo de app/."""
    from pathlib import Path
    for arquivo in Path("app").rglob("*.py"):
        assert "token-falso-de-teste" not in arquivo.read_text(encoding="utf-8")

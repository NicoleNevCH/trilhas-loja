"""Testes da extração (extract.py): nome com data/hora, nunca sobrescrever, falha atômica."""
import json
from datetime import datetime

from app import extract
from app.api_client import ApiUnavailableError


class ClienteFalso:
    def __init__(self, falhar_em=None):
        self.falhar_em = falhar_em

    def buscar_todos(self, recurso):
        if recurso == self.falhar_em:
            raise ApiUnavailableError("API fora do ar")
        return {recurso: [{"id": 1}], "total": 1, "skip": 0, "limit": 1}


MOMENTO = datetime(2026, 10, 26, 14, 30, 5)


def test_grava_arquivos_com_data_e_hora_no_nome(tmp_path):
    caminhos = extract.extrair(ClienteFalso(), tmp_path, MOMENTO)
    assert [p.name for p in caminhos] == [
        "users_2026-10-26_14-30-05.json", "carts_2026-10-26_14-30-05.json",
    ]
    assert all(p.parent == tmp_path / "2026-10-26" for p in caminhos)
    assert ":" not in caminhos[0].name  # ":" é proibido em nomes de arquivo no Windows
    assert json.loads(caminhos[0].read_text(encoding="utf-8"))["users"] == [{"id": 1}]


def test_nova_execucao_nunca_sobrescreve(tmp_path):
    primeira = extract.extrair(ClienteFalso(), tmp_path, MOMENTO)
    conteudo_original = primeira[0].read_text(encoding="utf-8")

    # Mesma data e hora de propósito: o pior caso (duas execuções no mesmo segundo).
    segunda = extract.extrair(ClienteFalso(), tmp_path, MOMENTO)

    assert {p.name for p in segunda}.isdisjoint({p.name for p in primeira})
    assert segunda[0].name == "users_2026-10-26_14-30-05_1.json"
    assert primeira[0].read_text(encoding="utf-8") == conteudo_original
    assert len(list((tmp_path / "2026-10-26").iterdir())) == 4


def test_execucao_em_outro_dia_vai_para_outra_pasta(tmp_path):
    extract.extrair(ClienteFalso(), tmp_path, MOMENTO)
    extract.extrair(ClienteFalso(), tmp_path, datetime(2026, 10, 27, 8, 0, 0))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-10-26", "2026-10-27"]


def test_se_uma_busca_falha_nenhum_arquivo_e_gravado(tmp_path):
    import pytest
    with pytest.raises(ApiUnavailableError):
        extract.extrair(ClienteFalso(falhar_em="carts"), tmp_path, MOMENTO)
    assert list(tmp_path.rglob("*.json")) == []  # nem o "users" ficou gravado


def test_main_mostra_erro_amigavel_e_retorna_1(monkeypatch, capsys):
    class ClienteQuebrado:
        def buscar_todos(self, recurso):
            raise ApiUnavailableError("API fora do ar")

    monkeypatch.setattr(extract, "DummyJsonClient", ClienteQuebrado)
    assert extract.main() == 1
    erro = capsys.readouterr().err
    assert "não foi possível buscar os dados" in erro
    assert "Nada foi gravado" in erro


def test_main_sucesso_grava_na_pasta_configurada(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(extract, "DummyJsonClient", ClienteFalso)
    assert extract.main() == 0
    assert len(list((tmp_path / "raw").rglob("users_*.json"))) == 1
    assert "Gravado:" in capsys.readouterr().out

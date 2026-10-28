"""Testes da extração: nome do arquivo, nunca sobrescrever e falha sem deixar lixo."""
import json
from datetime import datetime

import pytest

from app import extract
from app.api_client import ApiError

AGORA = datetime(2026, 10, 27, 14, 30, 5)


def api_falsa(recurso):
    return {recurso: [{"id": 1}], "total": 1}


@pytest.fixture(autouse=True)
def sem_internet(monkeypatch):
    monkeypatch.setattr(extract, "buscar_todos", api_falsa)


def test_grava_com_data_e_hora_no_nome(tmp_path):
    caminhos = extract.extrair(AGORA)
    assert [c.name for c in caminhos] == [
        "users_2026-10-27_14-30-05.json", "carts_2026-10-27_14-30-05.json",
    ]
    assert caminhos[0].parent == tmp_path / "raw" / "2026-10-27"
    assert ":" not in caminhos[0].name   # o Windows não aceita ":" no nome
    assert json.loads(caminhos[0].read_text(encoding="utf-8"))["users"] == [{"id": 1}]


def test_nova_execucao_nao_sobrescreve(tmp_path):
    caminhos = extract.extrair(AGORA)
    antes = caminhos[0].read_text(encoding="utf-8")

    # mesma data e hora de propósito (o pior caso): tem que dar erro, não sobrescrever
    with pytest.raises(FileExistsError):
        extract.extrair(AGORA)
    assert caminhos[0].read_text(encoding="utf-8") == antes


def test_outro_dia_vai_para_outra_pasta(tmp_path):
    extract.extrair(AGORA)
    extract.extrair(datetime(2026, 10, 28, 8, 0, 0))
    assert sorted(p.name for p in (tmp_path / "raw").iterdir()) == ["2026-10-27", "2026-10-28"]


def test_se_a_api_falha_nada_e_gravado(tmp_path, monkeypatch):
    def api_quebrada(recurso):
        if recurso == "carts":
            raise ApiError("API fora do ar")
        return api_falsa(recurso)

    monkeypatch.setattr(extract, "buscar_todos", api_quebrada)
    with pytest.raises(ApiError):
        extract.extrair(AGORA)
    assert list((tmp_path / "raw").rglob("*.json")) == []   # nem o "users" ficou gravado


def test_main_mostra_erro_amigavel(monkeypatch, capsys):
    def api_quebrada(recurso):
        raise ApiError("API fora do ar")

    monkeypatch.setattr(extract, "buscar_todos", api_quebrada)
    assert extract.main() == 1
    erro = capsys.readouterr().err
    assert "não foi possível buscar os dados" in erro and "Nada foi gravado" in erro


def test_main_com_sucesso(tmp_path, capsys):
    assert extract.main() == 0
    assert len(list((tmp_path / "raw").rglob("users_*.json"))) == 1
    assert "Gravado:" in capsys.readouterr().out
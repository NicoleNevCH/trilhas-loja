"""Testes da carga (load.py) e do repositório: totais por cliente, arquivo mais recente, upsert."""
import json
from datetime import datetime

import pytest

from app import load, repositorio
from app.db import conectar


def test_totais_por_cliente(usuarios, carrinhos):
    clientes = {c["id"]: c for c in load.montar_clientes(usuarios, carrinhos)}

    emily = clientes[1]
    assert emily["nome_completo"] == "Emily Johnson"
    assert emily["valor_total_carrinhos"] == 12450.00   # 10000.50 + 2449.50
    assert emily["quantidade_total_itens"] == 20        # 12 + 8
    assert emily["sexo"] == "feminino"
    assert emily["estado"] == "Mississippi"
    assert emily["telefone"] == "+81 965-431-3024"

    assert clientes[2]["valor_total_carrinhos"] == 500.00
    assert clientes[2]["sexo"] == "masculino"


def test_cliente_sem_carrinho_tem_totais_zero(usuarios, carrinhos):
    sophia = {c["id"]: c for c in load.montar_clientes(usuarios, carrinhos)}[3]
    assert sophia["valor_total_carrinhos"] == 0
    assert sophia["quantidade_total_itens"] == 0


def test_soma_de_centavos_nao_gera_erro_de_float():
    usuarios = [{"id": 1, "firstName": "A", "lastName": "B", "age": 40, "gender": "male",
                 "phone": "+1 555", "address": {"state": "X"}}]
    # 0.1 + 0.2 = 0.30000000000000004 em float; o round(…, 2) corrige.
    carrinhos = [{"userId": 1, "total": 0.1, "totalQuantity": 1},
                 {"userId": 1, "total": 0.2, "totalQuantity": 1}]
    assert load.montar_clientes(usuarios, carrinhos)[0]["valor_total_carrinhos"] == 0.3


def test_localiza_o_arquivo_mais_recente(tmp_path):
    for pasta, nome in [
        ("2026-10-25", "users_2026-10-25_23-59-59.json"),
        ("2026-10-26", "users_2026-10-26_08-00-00.json"),
        ("2026-10-26", "users_2026-10-26_14-30-05.json"),
        ("2026-10-26", "users_2026-10-26_14-30-05_1.json"),  # colisão no mesmo segundo
    ]:
        (tmp_path / pasta).mkdir(exist_ok=True)
        (tmp_path / pasta / nome).write_text("{}")
    assert load.localizar_ultimo_arquivo(tmp_path, "users").name == "users_2026-10-26_14-30-05_1.json"


def test_sem_arquivos_orienta_a_rodar_a_extracao(tmp_path):
    with pytest.raises(FileNotFoundError) as erro:
        load.localizar_ultimo_arquivo(tmp_path, "users")
    assert "python -m app.extract" in str(erro.value)


def test_main_le_o_raw_e_grava_no_banco(tmp_path, usuarios, carrinhos, capsys):
    pasta = tmp_path / "raw" / "2026-10-26"
    pasta.mkdir(parents=True)
    (pasta / "users_2026-10-26_10-00-00.json").write_text(json.dumps({"users": usuarios}))
    (pasta / "carts_2026-10-26_10-00-00.json").write_text(json.dumps({"carts": carrinhos}))

    assert load.main() == 0
    with conectar() as conn:
        linhas = repositorio.listar_clientes(conn)
    assert len(linhas) == 3
    assert linhas[0]["valor_total_carrinhos"] == 12450.0


def test_main_sem_dados_retorna_erro(capsys):
    assert load.main() == 1
    assert "python -m app.extract" in capsys.readouterr().err


def test_recarregar_dados_preserva_decisoes_do_analista(usuarios, carrinhos):
    clientes = load.montar_clientes(usuarios, carrinhos)
    with conectar() as conn:
        repositorio.upsert_clientes(conn, clientes)
        repositorio.confirmar_trilhas(conn, 1, ["Alto valor"], datetime(2026, 10, 26, 9, 0))

    # Segunda carga, com o cliente 1 mudando de idade: não pode apagar a confirmação.
    clientes[0]["idade"] = 29
    with conectar() as conn:
        repositorio.upsert_clientes(conn, clientes)
        assert repositorio.buscar_cliente(conn, 1)["idade"] == 29
        assert repositorio.buscar_confirmacao(conn, 1)[1] == ["Alto valor"]
        assert len(repositorio.listar_clientes(conn)) == 3  # sem duplicar


def test_reajuste_mantem_a_data_da_primeira_confirmacao(usuarios, carrinhos):
    with conectar() as conn:
        repositorio.upsert_clientes(conn, load.montar_clientes(usuarios, carrinhos))
        repositorio.confirmar_trilhas(conn, 1, ["Alto valor"], datetime(2026, 10, 26, 9, 0))
        repositorio.confirmar_trilhas(conn, 1, ["Público jovem", "Alto valor"], datetime(2026, 11, 2, 9, 0))
        data, trilhas = repositorio.buscar_confirmacao(conn, 1)
    assert str(data) == "2026-10-26"                      # início do cronograma não muda
    assert trilhas == ["Alto valor", "Público jovem"]      # trilhas novas, em ordem de prioridade

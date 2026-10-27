"""Testes do cronograma (schedule.py): dia da semana, 3 semanas por trilha, uma trilha por vez."""
from datetime import date

import pytest

from app import config
from app.config import ConfigError
from app.schedule import (
    ClienteConfirmado, filtrar_periodo, gerar_cronograma,
    gerar_envios_do_cliente, proxima_data_do_dia,
)
from app.tracks import ALTO_VALOR, GERAL, JOVEM, QUANTIDADE

SEGUNDA, QUARTA = 0, 2


def cliente(cid=1, nome="Emily Johnson", confirmado=date(2026, 10, 26), trilhas=(ALTO_VALOR,)):
    return ClienteConfirmado(cid, nome, "+81 965-431-3024", confirmado, tuple(trilhas))


def test_proxima_data_do_dia():
    segunda = date(2026, 10, 26)
    assert segunda.weekday() == SEGUNDA
    assert proxima_data_do_dia(segunda, SEGUNDA) == segunda                   # mesmo dia vale
    assert proxima_data_do_dia(segunda, QUARTA) == date(2026, 10, 28)         # adiante na semana
    assert proxima_data_do_dia(date(2026, 10, 28), SEGUNDA) == date(2026, 11, 2)  # "virou" a semana


def test_uma_trilha_tem_tres_mensagens_uma_por_semana_no_mesmo_dia():
    envios = gerar_envios_do_cliente(cliente(), SEGUNDA)
    assert [e.numero_mensagem for e in envios] == [1, 2, 3]
    assert [e.data for e in envios] == [date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 9)]
    assert {e.data.weekday() for e in envios} == {SEGUNDA}


def test_uma_trilha_de_cada_vez_na_ordem_de_prioridade():
    # Trilhas fora de ordem de propósito: o cronograma deve reordenar por prioridade.
    envios = gerar_envios_do_cliente(cliente(trilhas=(JOVEM, ALTO_VALOR, QUANTIDADE)), SEGUNDA)
    assert [(e.trilha, e.numero_mensagem) for e in envios] == [
        (ALTO_VALOR, 1), (ALTO_VALOR, 2), (ALTO_VALOR, 3),
        (QUANTIDADE, 1), (QUANTIDADE, 2), (QUANTIDADE, 3),
        (JOVEM, 1), (JOVEM, 2), (JOVEM, 3),
    ]
    # 9 mensagens em 9 semanas seguidas, sem semanas vazias nem sobrepostas.
    semanas = [(e.data - envios[0].data).days // 7 for e in envios]
    assert semanas == list(range(9))


def test_primeiro_envio_respeita_o_dia_da_semana_configurado():
    # Confirmado numa segunda, dia de envio quarta -> primeiro envio na quarta seguinte.
    envios = gerar_envios_do_cliente(cliente(), QUARTA)
    assert envios[0].data == date(2026, 10, 28)
    assert envios[0].data.weekday() == QUARTA


def test_texto_traz_o_primeiro_nome():
    envios = gerar_envios_do_cliente(cliente(nome="Emily Johnson"), SEGUNDA)
    assert envios[0].texto.startswith("Olá, Emily! Você é um dos nossos clientes especiais")
    assert "{nome}" not in envios[0].texto


def test_cronograma_junta_clientes_e_ordena_por_data():
    envios = gerar_cronograma(
        [cliente(cid=2, nome="Bob Lee", confirmado=date(2026, 11, 2), trilhas=(GERAL,)),
         cliente(cid=1)],
        SEGUNDA,
    )
    datas = [e.data for e in envios]
    assert datas == sorted(datas)
    # Em 2026-11-02 há mensagem 2 do cliente 1 e mensagem 1 do cliente 2.
    do_dia = [(e.cliente_id, e.numero_mensagem) for e in envios if e.data == date(2026, 11, 2)]
    assert do_dia == [(1, 2), (2, 1)]


def test_filtrar_periodo_e_inclusivo():
    envios = gerar_envios_do_cliente(cliente(), SEGUNDA)
    assert len(filtrar_periodo(envios, date(2026, 10, 26), date(2026, 11, 2))) == 2
    assert filtrar_periodo(envios, date(2026, 12, 1), date(2026, 12, 31)) == []


@pytest.mark.parametrize("texto, esperado", [
    ("segunda", 0), ("Terça", 1), ("terca-feira", 1), ("QUARTA", 2),
    ("quinta feira", 3), ("sexta", 4), ("sábado", 5), ("domingo", 6),
])
def test_dia_da_semana_configuravel(monkeypatch, texto, esperado):
    monkeypatch.setenv("DIA_SEMANA_ENVIO", texto)
    assert config.dia_semana_envio() == esperado


def test_dia_da_semana_invalido(monkeypatch):
    monkeypatch.setenv("DIA_SEMANA_ENVIO", "feriado")
    with pytest.raises(ConfigError):
        config.dia_semana_envio()

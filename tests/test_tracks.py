"""Testes das regras de trilhas (tracks.py): limites, múltiplas trilhas, motivos."""
import pytest

from app.tracks import (
    ALTO_VALOR, GERAL, INCENTIVO, JOVEM, QUANTIDADE,
    formatar_reais, ordenar_por_prioridade, sugerir_trilhas,
)


def nomes(sugestoes):
    return [s.trilha for s in sugestoes]


# Cada linha: (idade, valor, itens, trilha que DEVE aparecer, trilha que NÃO deve).
# Os valores ficam colados nos limites para pegar erros de "<" versus "<=".
@pytest.mark.parametrize("idade, valor, itens, presente, ausente", [
    (40, 10_000.00, 1, ALTO_VALOR, None),       # exatamente 10.000 entra (>=)
    (40, 9_999.99, 1, None, ALTO_VALOR),        # um centavo abaixo não entra
    (40, 5_000, 15, QUANTIDADE, None),          # exatamente 15 itens entra (>=)
    (40, 5_000, 14, None, QUANTIDADE),
    (40, 999.99, 1, INCENTIVO, None),           # abaixo de 1.000 entra (<)
    (40, 1_000.00, 1, None, INCENTIVO),         # exatamente 1.000 NÃO entra
    (29, 5_000, 1, JOVEM, None),                # 29 anos entra (<30)
    (30, 5_000, 1, None, JOVEM),                # exatamente 30 NÃO entra
])
def test_limites_das_regras(idade, valor, itens, presente, ausente):
    resultado = nomes(sugerir_trilhas(idade, valor, itens))
    if presente:
        assert presente in resultado
    if ausente:
        assert ausente not in resultado


def test_cliente_pode_ter_varias_trilhas_em_ordem_de_prioridade():
    resultado = sugerir_trilhas(idade=25, valor_total=12_450, total_itens=20)
    assert nomes(resultado) == [ALTO_VALOR, QUANTIDADE, JOVEM]
    assert [s.prioridade for s in resultado] == [1, 2, 4]


def test_geral_so_quando_nenhuma_outra_se_aplica():
    # 40 anos, R$ 5.000, 5 itens: nenhuma das quatro regras -> Geral
    assert nomes(sugerir_trilhas(40, 5_000, 5)) == [GERAL]
    # Se qualquer outra serve, Geral NÃO aparece junto.
    assert GERAL not in nomes(sugerir_trilhas(25, 5_000, 5))


def test_cliente_sem_carrinho_cai_em_incentivo():
    assert INCENTIVO in nomes(sugerir_trilhas(40, 0, 0))


def test_motivos_legiveis():
    por_trilha = {s.trilha: s.motivo for s in sugerir_trilhas(25, 12_450, 20)}
    assert por_trilha[ALTO_VALOR] == "valor total R$ 12.450,00 ≥ R$ 10.000,00"
    assert por_trilha[QUANTIDADE] == "20 itens ≥ 15 itens"
    assert por_trilha[JOVEM] == "idade 25 < 30 anos"
    assert sugerir_trilhas(40, 450, 1)[0].motivo == "valor total R$ 450,00 < R$ 1.000,00"


def test_formatar_reais():
    assert formatar_reais(12450) == "R$ 12.450,00"
    assert formatar_reais(0.5) == "R$ 0,50"
    assert formatar_reais(1234567.891) == "R$ 1.234.567,89"


def test_ordenar_por_prioridade_remove_duplicatas():
    assert ordenar_por_prioridade([JOVEM, ALTO_VALOR, JOVEM]) == [ALTO_VALOR, JOVEM]

"""
Classificação dos clientes em trilhas.

Este módulo é "puro": só recebe números e devolve resultados, sem tocar em banco,
rede ou arquivos. Isso o torna fácil de testar e de explicar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Limites das regras. Ficam como constantes nomeadas (e não "números mágicos"
# espalhados) para que mudar uma regra seja alterar UMA linha aqui.
# ---------------------------------------------------------------------------
LIMITE_ALTO_VALOR = 10_000    # trilha 1: valor total >= 10.000
LIMITE_ITENS = 15             # trilha 2: itens >= 15
LIMITE_INCENTIVO = 1_000      # trilha 3: valor total < 1.000
LIMITE_IDADE_JOVEM = 30       # trilha 4: idade < 30

# Nomes das trilhas (exatamente como na tabela do enunciado).
ALTO_VALOR = "Alto valor"
QUANTIDADE = "Compra em quantidade"
INCENTIVO = "Incentivo"
JOVEM = "Público jovem"
GERAL = "Geral"

# A ORDEM desta tupla É a ordem de prioridade (1 = mais prioritária). O cliente faz
# uma trilha de cada vez nessa ordem, então tudo que precisa ordenar usa esta tupla.
TRILHAS = (ALTO_VALOR, QUANTIDADE, INCENTIVO, JOVEM, GERAL)

# {"Alto valor": 1, "Compra em quantidade": 2, ...}
PRIORIDADE = {nome: posicao for posicao, nome in enumerate(TRILHAS, start=1)}


@dataclass(frozen=True)
class Sugestao:
    """Uma trilha sugerida para o cliente, com o motivo legível.

    `frozen=True` torna o objeto imutável (não dá para alterar depois de criado),
    o que evita bugs de alguém mudar uma sugestão sem querer.
    """

    trilha: str
    prioridade: int
    motivo: str


def formatar_reais(valor: float | None) -> str:
    """Formata no padrão brasileiro: 12450 -> 'R$ 12.450,00'.

    Não usamos o módulo `locale` porque ele depende do idioma instalado no sistema
    (e no Windows/Docker costuma não ter pt_BR). Em vez disso formatamos no padrão
    americano ('12,450.00') e TROCAMOS os separadores usando um marcador temporário
    ('X'), senão a vírgula viraria ponto e depois voltaria a ser vírgula.
    """
    if valor is None:
        return "—"
    americano = f"{valor:,.2f}"                      # '12,450.00'
    brasileiro = americano.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {brasileiro}"


def sugerir_trilhas(idade: int, valor_total: float, total_itens: int) -> list[Sugestao]:
    """Devolve TODAS as trilhas em que o cliente se encaixa, já em ordem de prioridade.

    - Um cliente pode cair em várias trilhas (ex.: alto valor E jovem).
    - "Geral" só aparece quando NENHUMA das quatro anteriores serviu.
    - Cada Sugestao traz o motivo, ex.: 'valor total R$ 12.450,00 ≥ R$ 10.000,00'.
    """
    sugestoes: list[Sugestao] = []

    # As quatro regras são testadas na ordem da tabela de prioridade. Como são `if`
    # independentes (e não `elif`), vários podem ser verdadeiros ao mesmo tempo.
    if valor_total >= LIMITE_ALTO_VALOR:
        sugestoes.append(Sugestao(
            ALTO_VALOR, PRIORIDADE[ALTO_VALOR],
            f"valor total {formatar_reais(valor_total)} ≥ {formatar_reais(LIMITE_ALTO_VALOR)}",
        ))

    if total_itens >= LIMITE_ITENS:
        sugestoes.append(Sugestao(
            QUANTIDADE, PRIORIDADE[QUANTIDADE],
            f"{total_itens} itens ≥ {LIMITE_ITENS} itens",
        ))

    if valor_total < LIMITE_INCENTIVO:
        # Cliente sem nenhum carrinho tem valor total 0 e, portanto, cai aqui.
        sugestoes.append(Sugestao(
            INCENTIVO, PRIORIDADE[INCENTIVO],
            f"valor total {formatar_reais(valor_total)} < {formatar_reais(LIMITE_INCENTIVO)}",
        ))

    if idade < LIMITE_IDADE_JOVEM:
        sugestoes.append(Sugestao(
            JOVEM, PRIORIDADE[JOVEM],
            f"idade {idade} < {LIMITE_IDADE_JOVEM} anos",
        ))

    # "Geral" = rede de segurança: só entra se a lista ainda está vazia.
    if not sugestoes:
        sugestoes.append(Sugestao(
            GERAL, PRIORIDADE[GERAL],
            "não se encaixou em nenhuma das trilhas anteriores",
        ))

    return sugestoes


def ordenar_por_prioridade(trilhas: Iterable[str]) -> list[str]:
    """Ordena nomes de trilhas pela prioridade da tabela (sem duplicatas)."""
    # `set` remove duplicatas; `sorted` com `key=PRIORIDADE.__getitem__` ordena
    # cada nome pelo número da sua prioridade.
    return sorted(set(trilhas), key=PRIORIDADE.__getitem__)

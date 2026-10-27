"""
Etapa 2 — CARGA: lê o JSON bruto MAIS RECENTE e monta a tabela `clientes` no SQLite.

Uso:    python -m app.load

Nunca apaga as decisões do analista: `clientes` é atualizada com UPSERT e as
tabelas de confirmação ficam intactas (veja repositorio.upsert_clientes).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from app import config, repositorio
from app.db import conectar

# Tradução do campo `gender` do DummyJSON para a coluna `sexo` (em português).
SEXO_PT = {"female": "feminino", "male": "masculino"}


def localizar_ultimo_arquivo(pasta_raw: Path, recurso: str) -> Path:
    """Acha o arquivo mais recente de `recurso` em data/raw/*/.

    Os nomes têm data e hora no formato AAAA-MM-DD_HH-MM-SS, que ORDENA em ordem
    cronológica quando comparado como texto. Por isso basta ordenar os caminhos e
    pegar o último (o sufixo _1, _2 de colisões também ordena depois do original).
    """
    candidatos = sorted(pasta_raw.glob(f"*/{recurso}_*.json"))
    if not candidatos:
        raise FileNotFoundError(
            f"Nenhum arquivo '{recurso}_*.json' em {pasta_raw}. "
            f"Rode primeiro: python -m app.extract"
        )
    return candidatos[-1]


def ler_registros(caminho: Path, recurso: str) -> list[dict]:
    """Lê o JSON bruto e devolve a lista de registros (a chave tem o nome do recurso)."""
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)[recurso]


def montar_clientes(usuarios: list[dict], carrinhos: list[dict]) -> list[dict]:
    """Junta usuários e carrinhos: uma linha por cliente, com os totais dos carrinhos.

    O que significa cada total (decisões documentadas no README):
      - valor total  = soma do campo `total` dos carrinhos (valor ANTES de descontos);
      - total de itens = soma de `totalQuantity` (unidades, contando a quantidade de
        cada produto; não apenas quantos produtos diferentes).
    """
    # defaultdict: ao acessar um userId novo, já nasce como [0.0, 0] (valor, itens).
    # Assim clientes sem carrinho ficam com 0 e 0 sem tratamento especial.
    totais: dict[int, list[float]] = defaultdict(lambda: [0.0, 0])
    for carrinho in carrinhos:
        acumulado = totais[carrinho["userId"]]
        acumulado[0] += carrinho["total"]
        acumulado[1] += carrinho["totalQuantity"]

    clientes = []
    for usuario in usuarios:
        valor, itens = totais[usuario["id"]]
        clientes.append({
            "id": usuario["id"],
            "nome_completo": f"{usuario['firstName']} {usuario['lastName']}",
            "idade": usuario["age"],
            "sexo": SEXO_PT.get(usuario["gender"], usuario["gender"]),
            "estado": usuario["address"]["state"],
            "telefone": usuario["phone"],
            # round(..., 2): somar floats gera ruídos tipo 9999.999999999; arredondar
            # para centavos evita que um cliente "escape" de um limite por erro de float.
            "valor_total_carrinhos": round(valor, 2),
            "quantidade_total_itens": int(itens),
        })
    return clientes


def main() -> int:
    try:
        arquivo_usuarios = localizar_ultimo_arquivo(config.pasta_raw(), "users")
        arquivo_carrinhos = localizar_ultimo_arquivo(config.pasta_raw(), "carts")
        clientes = montar_clientes(
            ler_registros(arquivo_usuarios, "users"),
            ler_registros(arquivo_carrinhos, "carts"),
        )
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1

    with conectar() as conn:
        quantidade = repositorio.upsert_clientes(conn, clientes)

    print(f"Lidos: {arquivo_usuarios.name} e {arquivo_carrinhos.name}")
    print(f"{quantidade} clientes gravados em {config.caminho_db()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

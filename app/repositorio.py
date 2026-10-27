"""
Consultas ao banco (SQL), agrupadas num lugar só.

Mantê-las aqui, separadas das rotas web, deixa o `main.py` focado em HTTP e este
arquivo focado em dados. Todas as funções recebem a conexão (`conn`) já aberta por
`db.conectar()`, que cuida de commit/rollback.

Segurança: TODOS os valores entram por parâmetros (`?` ou `:nome`), nunca por
concatenação de texto no SQL. Isso impede SQL injection.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Iterable

from app.schedule import ClienteConfirmado, Envio
from app.tracks import ordenar_por_prioridade

# ----------------------------------------------------------------- clientes


def upsert_clientes(conn: sqlite3.Connection, clientes: Iterable[dict]) -> int:
    """Insere clientes novos e ATUALIZA os que já existem (pelo `id`).

    "UPSERT" = INSERT + UPDATE. Em vez de apagar a tabela e recriar (o que, com a
    chave estrangeira, destruiria as decisões do analista), atualizamos linha a linha.
    `excluded.<coluna>` é o valor que tentamos inserir e que conflitou com a linha existente.
    """
    sql = """
        INSERT INTO clientes (id, nome_completo, idade, sexo, estado, telefone,
                              valor_total_carrinhos, quantidade_total_itens)
        VALUES (:id, :nome_completo, :idade, :sexo, :estado, :telefone,
                :valor_total_carrinhos, :quantidade_total_itens)
        ON CONFLICT(id) DO UPDATE SET
            nome_completo          = excluded.nome_completo,
            idade                  = excluded.idade,
            sexo                   = excluded.sexo,
            estado                 = excluded.estado,
            telefone               = excluded.telefone,
            valor_total_carrinhos  = excluded.valor_total_carrinhos,
            quantidade_total_itens = excluded.quantidade_total_itens
    """
    lista = list(clientes)
    conn.executemany(sql, lista)
    return len(lista)


def listar_clientes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM clientes ORDER BY id").fetchall()


def buscar_cliente(conn: sqlite3.Connection, cliente_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()


# ------------------------------------------------------------- confirmações


def mapa_confirmacoes(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """{cliente_id: [trilhas confirmadas em ordem de prioridade]} só de quem foi confirmado."""
    mapa: dict[int, list[str]] = {}
    for linha in conn.execute("SELECT cliente_id, trilha FROM trilhas_confirmadas"):
        mapa.setdefault(linha["cliente_id"], []).append(linha["trilha"])
    return {cid: ordenar_por_prioridade(trilhas) for cid, trilhas in mapa.items()}


def buscar_confirmacao(conn: sqlite3.Connection, cliente_id: int) -> tuple[date, list[str]] | None:
    """(data da 1ª confirmação, trilhas confirmadas) ou None se o cliente não foi confirmado."""
    linha = conn.execute(
        "SELECT confirmado_em FROM confirmacoes WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()
    if linha is None:
        return None
    trilhas = [
        r["trilha"]
        for r in conn.execute(
            "SELECT trilha FROM trilhas_confirmadas WHERE cliente_id = ?", (cliente_id,)
        )
    ]
    return date.fromisoformat(linha["confirmado_em"]), ordenar_por_prioridade(trilhas)


def confirmar_trilhas(
    conn: sqlite3.Connection, cliente_id: int, trilhas: Iterable[str], agora: datetime
) -> None:
    """Grava a decisão do analista (confirmar OU ajustar) para um cliente.

    Tudo acontece na MESMA transação (o commit é feito por `db.conectar`): ou grava
    tudo ou nada.
    """
    # 1) Registro da confirmação. Na PRIMEIRA vez grava `confirmado_em` (início do
    #    cronograma). Nas seguintes (ajustes) o ON CONFLICT só atualiza `atualizado_em`,
    #    preservando a data original.
    conn.execute(
        """
        INSERT INTO confirmacoes (cliente_id, confirmado_em, atualizado_em)
        VALUES (?, ?, ?)
        ON CONFLICT(cliente_id) DO UPDATE SET atualizado_em = excluded.atualizado_em
        """,
        (cliente_id, agora.date().isoformat(), agora.isoformat(timespec="seconds")),
    )
    # 2) Substitui o conjunto de trilhas: apaga as antigas e insere as novas.
    conn.execute("DELETE FROM trilhas_confirmadas WHERE cliente_id = ?", (cliente_id,))
    conn.executemany(
        "INSERT INTO trilhas_confirmadas (cliente_id, trilha) VALUES (?, ?)",
        [(cliente_id, trilha) for trilha in trilhas],
    )


def listar_confirmados(conn: sqlite3.Connection) -> list[ClienteConfirmado]:
    """Clientes confirmados, no formato que o cronograma espera."""
    trilhas_por_cliente = mapa_confirmacoes(conn)
    linhas = conn.execute(
        """
        SELECT c.id, c.nome_completo, c.telefone, f.confirmado_em
        FROM confirmacoes f
        JOIN clientes c ON c.id = f.cliente_id
        ORDER BY c.id
        """
    ).fetchall()
    return [
        ClienteConfirmado(
            id=linha["id"],
            nome_completo=linha["nome_completo"],
            telefone=linha["telefone"],
            confirmado_em=date.fromisoformat(linha["confirmado_em"]),
            trilhas=tuple(trilhas_por_cliente.get(linha["id"], [])),
        )
        for linha in linhas
    ]


# ---------------------------------------------------------------- histórico


def registrar_envio(
    conn: sqlite3.Connection, envio: Envio, requisicao_json: str, simulado_em: datetime
) -> bool:
    """Grava no histórico a requisição simulada. Devolve True se gravou, False se já existia.

    `INSERT OR IGNORE` + a restrição UNIQUE da tabela = idempotência: simular duas
    vezes o mesmo envio não duplica. `rowcount` é 1 quando inseriu e 0 quando ignorou.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO historico_envios
            (cliente_id, cliente_nome, trilha, numero_mensagem, data_prevista,
             mensagem, requisicao_json, simulado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            envio.cliente_id, envio.cliente_nome, envio.trilha, envio.numero_mensagem,
            envio.data.isoformat(), envio.texto, requisicao_json,
            simulado_em.isoformat(timespec="seconds"),
        ),
    )
    return cursor.rowcount == 1


def chaves_ja_simuladas(conn: sqlite3.Connection) -> set[tuple[int, str, int, str]]:
    """Conjunto de (cliente, trilha, nº da mensagem, data) já simulados; marca a tela do cronograma."""
    return {
        (r["cliente_id"], r["trilha"], r["numero_mensagem"], r["data_prevista"])
        for r in conn.execute(
            "SELECT cliente_id, trilha, numero_mensagem, data_prevista FROM historico_envios"
        )
    }


def listar_historico(conn: sqlite3.Connection, limite: int = 200) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM historico_envios ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()

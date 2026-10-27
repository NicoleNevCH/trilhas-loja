"""
Conexão com o SQLite e criação das tabelas.

Por que SQLite? Já vem com o Python (módulo `sqlite3`), é um único arquivo e não
precisa instalar nem configurar servidor. Para um protótipo é a escolha mais simples.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app import config

# O esquema usa "CREATE TABLE IF NOT EXISTS": rodar de novo não apaga nada.
ESQUEMA = """
-- Uma linha por cliente (requisito do teste). É recarregada a cada `python -m app.load`
-- com UPSERT (insere ou atualiza), sem nunca apagar as decisões do analista abaixo.
CREATE TABLE IF NOT EXISTS clientes (
    id                      INTEGER PRIMARY KEY,   -- mesmo id do DummyJSON
    nome_completo           TEXT    NOT NULL,
    idade                   INTEGER NOT NULL,
    sexo                    TEXT    NOT NULL,
    estado                  TEXT    NOT NULL,
    telefone                TEXT    NOT NULL,      -- como veio da API (ex.: +81 965-431-3024)
    valor_total_carrinhos   REAL    NOT NULL,      -- soma de `total` de todos os carrinhos
    quantidade_total_itens  INTEGER NOT NULL       -- soma de `totalQuantity` dos carrinhos
);

-- Decisão do analista: uma linha por cliente CONFIRMADO. Só quem está aqui entra no
-- cronograma. `confirmado_em` é a data da PRIMEIRA confirmação e marca o início do
-- cronograma (não muda se o analista ajustar as trilhas depois). `atualizado_em` guarda
-- a data/hora da última decisão (auditoria).
CREATE TABLE IF NOT EXISTS confirmacoes (
    cliente_id     INTEGER PRIMARY KEY REFERENCES clientes(id),
    confirmado_em  TEXT NOT NULL,   -- AAAA-MM-DD
    atualizado_em  TEXT NOT NULL    -- AAAA-MM-DDTHH:MM:SS
);

-- As trilhas que o analista confirmou (pode ser mais de uma por cliente).
-- A chave primária composta impede a mesma trilha duas vezes para o mesmo cliente.
CREATE TABLE IF NOT EXISTS trilhas_confirmadas (
    cliente_id  INTEGER NOT NULL REFERENCES clientes(id),
    trilha      TEXT    NOT NULL,
    PRIMARY KEY (cliente_id, trilha)
);

-- Histórico das requisições SIMULADAS (nada é enviado de verdade).
-- A restrição UNIQUE evita duplicar: clicar duas vezes em "Simular envios de hoje"
-- não grava a mesma mensagem duas vezes para o mesmo cliente no mesmo dia.
CREATE TABLE IF NOT EXISTS historico_envios (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id       INTEGER NOT NULL,
    cliente_nome     TEXT    NOT NULL,
    trilha           TEXT    NOT NULL,
    numero_mensagem  INTEGER NOT NULL,      -- 1, 2 ou 3 dentro da trilha
    data_prevista    TEXT    NOT NULL,      -- dia do envio (AAAA-MM-DD)
    mensagem         TEXT    NOT NULL,      -- texto final, com {nome} já substituído
    requisicao_json  TEXT    NOT NULL,      -- a requisição HTTP que SERIA enviada
    simulado_em      TEXT    NOT NULL,      -- quando o botão foi clicado
    UNIQUE (cliente_id, trilha, numero_mensagem, data_prevista)
);
"""


@contextmanager
def conectar(caminho: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Abre uma conexão, garante as tabelas e faz COMMIT/ROLLBACK sozinho.

    Uso:
        with conectar() as conn:
            conn.execute(...)
    Se o bloco terminar sem erro -> commit. Se levantar exceção -> rollback
    (a transação inteira é desfeita) e a exceção continua subindo.

    Abrimos UMA conexão POR operação (e não uma global) porque o FastAPI executa
    cada requisição numa thread diferente e conexões do sqlite3 não podem ser
    compartilhadas entre threads. Abrir um arquivo SQLite é barato.
    """
    destino = Path(caminho) if caminho else config.caminho_db()
    destino.parent.mkdir(parents=True, exist_ok=True)  # cria data/ se não existir

    conn = sqlite3.connect(destino)
    # Com row_factory = Row, as linhas viram "dicionários": linha["nome_completo"].
    conn.row_factory = sqlite3.Row
    # O SQLite NÃO impõe chaves estrangeiras por padrão; este PRAGMA liga a checagem
    # (por exemplo: não dá para confirmar trilhas de um cliente que não existe).
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(ESQUEMA)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

"""
Etapa 1 — EXTRAÇÃO: busca clientes e carrinhos e grava o JSON bruto em disco.

Uso:    python -m app.extract

Resultado (exemplo):
    data/raw/2026-10-26/users_2026-10-26_14-30-05.json
    data/raw/2026-10-26/carts_2026-10-26_14-30-05.json

Garantias pedidas no enunciado:
    - data e hora no nome do arquivo;
    - uma nova execução NUNCA apaga nem sobrescreve arquivos anteriores.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from app import config
from app.api_client import ApiError, DummyJsonClient

RECURSOS = ("users", "carts")


def salvar_json(dados: dict, pasta_raw: Path, recurso: str, momento: datetime) -> Path:
    """Grava `dados` em <pasta_raw>/AAAA-MM-DD/<recurso>_AAAA-MM-DD_HH-MM-SS.json.

    NUNCA sobrescreve: o arquivo é aberto no modo "x" (exclusive creation), que
    levanta FileExistsError se o nome já existir. Se isso acontecer (duas execuções
    no mesmo segundo), tentamos de novo com sufixo _1, _2... até achar um nome livre.

    Por que "HH-MM-SS" e não "HH:MM:SS"? O Windows NÃO aceita ":" em nome de arquivo.
    """
    pasta_do_dia = pasta_raw / momento.strftime("%Y-%m-%d")
    pasta_do_dia.mkdir(parents=True, exist_ok=True)  # exist_ok: não falha se já existir

    base = f"{recurso}_{momento.strftime('%Y-%m-%d_%H-%M-%S')}"
    contador = 0
    while True:
        sufixo = "" if contador == 0 else f"_{contador}"
        caminho = pasta_do_dia / f"{base}{sufixo}.json"
        try:
            arquivo = open(caminho, "x", encoding="utf-8")
        except FileExistsError:
            contador += 1
            continue  # nome ocupado -> tenta o próximo

        try:
            with arquivo:  # o `with` fecha o arquivo ao sair, com ou sem erro
                # ensure_ascii=False mantém acentos legíveis; indent=2 facilita a leitura.
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        except BaseException:
            # Se algo falhou NO MEIO da escrita (disco cheio, Ctrl+C), apagamos o
            # arquivo pela metade (só o que acabamos de criar) e repassamos o erro.
            caminho.unlink(missing_ok=True)
            raise
        return caminho


def extrair(cliente: DummyJsonClient, pasta_raw: Path, agora: datetime) -> list[Path]:
    """Busca TODOS os recursos e só então grava os arquivos.

    A ordem importa: primeiro buscamos tudo; se QUALQUER busca falhar, a exceção sobe
    antes de gravarmos qualquer arquivo. Assim nunca sobra um "users" sem o "carts"
    correspondente. Os dois arquivos compartilham o mesmo `agora` (mesmo carimbo).
    """
    dados = {recurso: cliente.buscar_todos(recurso) for recurso in RECURSOS}
    return [salvar_json(dados[recurso], pasta_raw, recurso, agora) for recurso in RECURSOS]


def main() -> int:
    """Ponto de entrada. Devolve o código de saída: 0 = sucesso, 1 = erro."""
    try:
        caminhos = extrair(DummyJsonClient(), config.pasta_raw(), datetime.now())
    except ApiError as erro:
        # Erro esperado (API fora do ar etc.): mensagem curta, sem traceback assustador.
        print(f"ERRO: não foi possível buscar os dados.\n  {erro}", file=sys.stderr)
        print("Nada foi gravado. Tente novamente em alguns instantes.", file=sys.stderr)
        return 1
    except OSError as erro:
        print(f"ERRO ao gravar os arquivos: {erro}", file=sys.stderr)
        return 1

    for caminho in caminhos:
        print(f"Gravado: {caminho}")
    return 0


if __name__ == "__main__":
    # `sys.exit(main())` repassa 0/1 ao sistema; scripts e CI usam esse código.
    sys.exit(main())

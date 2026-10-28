"""Busca os dados na API e grava o JSON bruto em data/raw/AAAA-MM-DD/.

Uso:  python -m app.extract
"""
import json
import sys
from datetime import datetime

from app import config
from app.api_client import ApiError, buscar_todos

RECURSOS = ("users", "carts")


def salvar_json(dados, recurso, agora):
    """Grava em data/raw/2026-10-27/users_2026-10-27_14-30-05.json"""
    pasta = config.pasta_raw() / agora.strftime("%Y-%m-%d")
    pasta.mkdir(parents=True, exist_ok=True)

    # No Windows não pode ":" em nome de arquivo, por isso HH-MM-SS.
    caminho = pasta / f"{recurso}_{agora.strftime('%Y-%m-%d_%H-%M-%S')}.json"

    # Modo "x" = só cria se o arquivo NÃO existir. Se existir, dá erro em vez de
    # sobrescrever. Assim uma nova execução nunca apaga a anterior.
    with open(caminho, "x", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    return caminho


def extrair(agora):
    # Busca tudo ANTES de gravar: se a API falhar, nenhum arquivo é criado.
    dados = {recurso: buscar_todos(recurso) for recurso in RECURSOS}
    return [salvar_json(dados[recurso], recurso, agora) for recurso in RECURSOS]


def main():
    try:
        caminhos = extrair(datetime.now())
    except ApiError as erro:
        print(f"ERRO: não foi possível buscar os dados.\n  {erro}\nNada foi gravado.", file=sys.stderr)
        return 1
    except FileExistsError:
        print("ERRO: já existe um arquivo com esta data e hora. Espere 1 segundo e rode de novo.",
              file=sys.stderr)
        return 1

    for caminho in caminhos:
        print(f"Gravado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
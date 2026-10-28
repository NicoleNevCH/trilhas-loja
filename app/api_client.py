"""Busca clientes e carrinhos na API pública DummyJSON."""
import time

import requests

URL_BASE = "https://dummyjson.com"
TAMANHO_PAGINA = 100   # quantos registros pedir por vez
TENTATIVAS = 3         # quantas vezes tentar se a API falhar
TIMEOUT = 10           # segundos esperando resposta, para nunca travar


class ApiError(Exception):
    """A API não respondeu ou devolveu algo que não dá para usar."""


def _get(url, params):
    """Faz o GET. Se a API estiver fora do ar, tenta de novo esperando cada vez mais."""
    motivo = ""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = requests.get(url, params=params, timeout=TIMEOUT)
        except requests.exceptions.RequestException as erro:
            # sem internet, timeout, conexão recusada...
            motivo = f"falha de rede ({type(erro).__name__})"
        else:
            if resposta.status_code >= 500:
                motivo = f"HTTP {resposta.status_code}"   # erro do servidor: vale tentar de novo
            elif resposta.status_code >= 400:
                # erro nosso (ex.: 404): repetir não adianta
                raise ApiError(f"A API respondeu HTTP {resposta.status_code} para {url}")
            else:
                try:
                    return resposta.json()
                except ValueError:
                    raise ApiError(f"A resposta de {url} não é um JSON válido")

        if tentativa < TENTATIVAS:
            time.sleep(2 ** (tentativa - 1))   # espera 1s, depois 2s

    raise ApiError(f"A API não respondeu após {TENTATIVAS} tentativas ({motivo}). URL: {url}")


def buscar_todos(recurso):
    """Busca todas as páginas de 'users' ou 'carts'.

    A API devolve {"users": [...], "total": 208, ...}. Pedimos 'limit' registros
    e vamos aumentando o 'skip' até juntar o 'total'.
    """
    url = f"{URL_BASE}/{recurso}"
    registros = []

    while True:
        pagina = _get(url, {"limit": TAMANHO_PAGINA, "skip": len(registros)})

        if not isinstance(pagina, dict) or not isinstance(pagina.get(recurso), list) \
                or not isinstance(pagina.get("total"), int):
            raise ApiError(f"Formato inesperado na resposta de {url}")

        registros.extend(pagina[recurso])
        # para quando juntou tudo (ou se a página veio vazia, para não ficar em loop)
        if not pagina[recurso] or len(registros) >= pagina["total"]:
            break

    if len(registros) < pagina["total"]:
        raise ApiError(f"Dados incompletos de '{recurso}': {len(registros)} de {pagina['total']}")

    return {recurso: registros, "total": len(registros)}
"""
Cliente da API pública DummyJSON, com paginação e tratamento de erro.

Como a paginação do DummyJSON funciona (documentação: https://dummyjson.com/docs):
    GET /users?limit=100&skip=0   -> {"users": [...], "total": 208, "skip": 0, "limit": 100}
    GET /users?limit=100&skip=100 -> próxima página ...
`total` é a quantidade de registros no servidor; `skip` é quantos pular. (A API também
aceita `limit=0` para devolver tudo de uma vez, mas paginar explicitamente funciona
com qualquer API paginada e não depende desse atalho.)

Tratamento de erro quando a API não responde (diferencial do teste):
    - timeout em toda requisição (nunca ficamos esperando para sempre);
    - nova tentativa com ESPERA CRESCENTE (backoff exponencial: 1s, 2s, 4s...) para
      falhas temporárias: erro de rede, timeout, HTTP 429 (muitas requisições) e 5xx;
    - sem nova tentativa para erros 4xx (ex.: 404): repetir não resolveria;
    - ao esgotar as tentativas levantamos um erro com mensagem clara em português.
"""
from __future__ import annotations

import time
from typing import Any, Callable

import requests

URL_BASE = "https://dummyjson.com"

# Códigos HTTP "temporários": vale a pena tentar de novo.
#   429 = Too Many Requests; 500 = erro interno; 502/503/504 = gateway/serviço fora.
CODIGOS_COM_NOVA_TENTATIVA = {429, 500, 502, 503, 504}


class ApiError(Exception):
    """Classe-mãe de todos os erros da API. Capturar `ApiError` pega qualquer um deles."""


class ApiUnavailableError(ApiError):
    """A API não respondeu (rede, timeout ou 5xx) mesmo depois de todas as tentativas."""


class ApiResponseError(ApiError):
    """A API respondeu, mas a resposta é inútil (4xx, JSON inválido, formato inesperado)."""


class DummyJsonClient:
    def __init__(
        self,
        url_base: str = URL_BASE,
        tamanho_pagina: int = 100,
        tentativas: int = 3,
        espera_inicial: float = 1.0,
        timeout: float = 10.0,
        sessao: Any = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url_base = url_base.rstrip("/")
        self.tamanho_pagina = tamanho_pagina
        self.tentativas = tentativas
        self.espera_inicial = espera_inicial
        self.timeout = timeout
        # `requests.Session` reaproveita a conexão TCP entre as requisições (mais rápido).
        # Os parâmetros `sessao` e `dormir` existem para os TESTES poderem injetar
        # versões falsas (sem internet e sem esperar de verdade).
        self.sessao = sessao or requests.Session()
        self.dormir = dormir

    # ------------------------------------------------------------------
    def _get(self, url: str, params: dict[str, Any]) -> Any:
        """GET com timeout e retentativas. Devolve o JSON já convertido (dict/list)."""
        ultimo_motivo = "sem detalhes"

        for tentativa in range(1, self.tentativas + 1):
            try:
                resposta = self.sessao.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as erro:
                # RequestException é a classe-mãe de ConnectionError, Timeout etc.
                ultimo_motivo = f"falha de rede ({type(erro).__name__})"
            else:
                status = resposta.status_code
                if status in CODIGOS_COM_NOVA_TENTATIVA:
                    ultimo_motivo = f"HTTP {status}"
                elif status >= 400:
                    # Erro "definitivo" (ex.: 404). Repetir seria perda de tempo.
                    raise ApiResponseError(f"A API respondeu HTTP {status} para {url}.")
                else:
                    try:
                        return resposta.json()
                    except ValueError as erro:  # JSON malformado
                        raise ApiResponseError(
                            f"A resposta de {url} não é um JSON válido."
                        ) from erro

            # Chegamos aqui = falha temporária. Se ainda há tentativas, esperamos.
            # Espera: 1s, 2s, 4s... (espera_inicial * 2^(tentativa-1)).
            if tentativa < self.tentativas:
                self.dormir(self.espera_inicial * 2 ** (tentativa - 1))

        raise ApiUnavailableError(
            f"A API não respondeu após {self.tentativas} tentativas "
            f"(último problema: {ultimo_motivo}). URL: {url}"
        )

    # ------------------------------------------------------------------
    def buscar_todos(self, recurso: str) -> dict[str, Any]:
        """Busca TODAS as páginas de `recurso` ('users' ou 'carts').

        Devolve um dict no mesmo formato de uma resposta da API:
            {"users": [... todos ...], "total": N, "skip": 0, "limit": N}
        """
        url = f"{self.url_base}/{recurso}"
        registros: list[Any] = []
        pular = 0

        while True:
            pagina = self._get(url, {"limit": self.tamanho_pagina, "skip": pular})

            # Valida o formato ANTES de usar: a lista de registros vem numa chave com
            # o mesmo nome do recurso ({"users": [...]} ou {"carts": [...]}).
            if not isinstance(pagina, dict) or not isinstance(pagina.get(recurso), list):
                raise ApiResponseError(
                    f"Formato inesperado na resposta de {url}: faltou a lista '{recurso}'."
                )

            itens = pagina[recurso]
            registros.extend(itens)
            pular += len(itens)
            total = pagina.get("total")

            # Condições de parada:
            #  - página vazia (evita laço infinito se a API se comportar mal);
            #  - já juntamos `total` registros.
            if not itens or (isinstance(total, int) and pular >= total):
                break

        # Conferência final: se a API disse que havia `total` registros e juntamos menos,
        # os dados estão incompletos. Melhor falhar do que gravar um JSON pela metade.
        if isinstance(total, int) and len(registros) < total:
            raise ApiResponseError(
                f"Dados incompletos de '{recurso}': recebidos {len(registros)} de {total}."
            )

        return {recurso: registros, "total": len(registros), "skip": 0, "limit": len(registros)}

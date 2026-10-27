"""
Configurações do projeto.

REGRA: tudo que muda de um ambiente para outro (caminhos, dia de envio, token de
acesso...) vem de VARIÁVEIS DE AMBIENTE. Nada disso é escrito direto no código.
Isso evita vazar segredos no GitHub e permite configurar o mesmo código em outro
computador (ou dentro do Docker) sem editar nenhum arquivo .py.

As funções abaixo leem a variável NA HORA DA CHAMADA (e não uma vez só, na
importação do módulo). Assim os testes conseguem trocar o valor com
`monkeypatch.setenv(...)` e o comportamento muda imediatamente.
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

# `load_dotenv()` procura um arquivo chamado ".env" a partir da pasta deste arquivo,
# subindo pelas pastas-mãe até a raiz do projeto, e copia as linhas CHAVE=valor
# para as variáveis de ambiente.
# Detalhes importantes:
#   - NÃO sobrescreve variáveis que já existem no ambiente (o que você definiu
#     com `set` no cmd ou `-e` no Docker tem prioridade sobre o arquivo);
#   - se o arquivo não existir, simplesmente não faz nada;
#   - o ".env" está no .gitignore, então o token real nunca vai para o GitHub.
load_dotenv()


class ConfigError(Exception):
    """Configuração ausente ou inválida (ex.: token da Botmaker não definido)."""


# Nomes dos dias da semana em português, na mesma ordem do `date.weekday()` do
# Python (0 = segunda ... 6 = domingo). Usamos esta tupla em vez de `locale`
# porque o idioma do Windows/Docker varia e `locale` não é confiável.
NOMES_DIAS_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

# Como o dia pode ser escrito na variável DIA_SEMANA_ENVIO (já sem acento e sem
# "-feira"; a função `_sem_acentos` e o `replace` em `dia_semana_envio` cuidam disso).
_DIAS_POR_NOME = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}


def _sem_acentos(texto: str) -> str:
    """Remove acentos: 'terça' -> 'terca'.

    NFKD separa a letra do acento ('ç' vira 'c' + cedilha combinante); depois
    descartamos os caracteres combinantes (os acentos) e juntamos o resto.
    """
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def caminho_db() -> Path:
    """Arquivo do banco SQLite. Padrão: data/loja.db (relativo à pasta do projeto)."""
    return Path(os.getenv("DB_PATH", "data/loja.db"))


def pasta_raw() -> Path:
    """Pasta onde o JSON bruto é gravado. Padrão: data/raw."""
    return Path(os.getenv("RAW_DIR", "data/raw"))


def dia_semana_envio() -> int:
    """Dia da semana dos envios (CONFIGURÁVEL), como número do Python (0=segunda).

    Variável: DIA_SEMANA_ENVIO. Aceita 'segunda', 'terça', 'terca-feira', 'Sexta'...
    Padrão: segunda.
    """
    bruto = os.getenv("DIA_SEMANA_ENVIO", "segunda")
    chave = _sem_acentos(bruto).strip().lower()
    # "terca-feira" / "terca feira" -> "terca"
    chave = chave.replace("-feira", "").replace(" feira", "").strip()
    if chave not in _DIAS_POR_NOME:
        validos = ", ".join(NOMES_DIAS_SEMANA)
        raise ConfigError(
            f"DIA_SEMANA_ENVIO={bruto!r} é inválido. Use um destes: {validos}."
        )
    return _DIAS_POR_NOME[chave]


def codigo_pais_padrao() -> str:
    """DDI usado quando o telefone do cliente vem SEM código de país. Padrão: 55 (Brasil)."""
    return os.getenv("CODIGO_PAIS_PADRAO", "55")


def variavel_obrigatoria(nome: str) -> str:
    """Lê uma variável de ambiente que PRECISA existir; senão levanta ConfigError.

    Usada para o token da Botmaker: falhar cedo e com mensagem clara é melhor do
    que montar uma requisição com token vazio.
    """
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise ConfigError(
            f"A variável de ambiente {nome} não está definida. "
            f"Defina-a (veja o arquivo .env.example) e tente de novo."
        )
    return valor

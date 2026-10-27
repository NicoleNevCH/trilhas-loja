"""
Envio SIMULADO por WhatsApp via API da Botmaker (v2.0).

Plataforma escolhida: Botmaker  (https://api.botmaker.com/v2.0/)

IMPORTANTE: este módulo NUNCA faz a chamada de rede. Ele só MONTA a requisição
(método, URL, cabeçalhos e corpo) exatamente como a documentação pede, para ser
gravada no histórico.

Endpoint usado — "Enviar Notificação" (send-notification), documentação da Botmaker
"Como enviar notificações por meio da API?":
    POST https://api.botmaker.com/v2.0/notifications

Cabeçalhos (seção 2.2 da documentação):
    access-token: <TOKEN>          <- vem da variável de ambiente, nunca do código
    Content-Type: application/json
    Accept: application/json

Corpo (NotificationRequest, seção 5.1) e contato (NotificationContactRequest, 5.2):
    name            (obrigatório) nome da notificação
    channelId       (obrigatório) ID do canal de WhatsApp (obtido em GET /channels)
    campaign        (opcional)    nome/ID da campanha, ou null = campanha padrão
    intentIdOrName  (opcional)    intent/template a disparar
    contacts        (obrigatório) lista de contatos, cada um com:
        contactId       (obrigatório) telefone COM código do país, só dígitos
                        (a doc dá o exemplo "5511955667788")
        variables       (opcional)    variáveis definidas antes de executar o intent
        webhookPayload  (opcional)    texto livre devolvido no webhook (rastreamento)

Por que "notifications" e não uma mensagem de texto livre? A própria documentação
explica que o WhatsApp só permite texto livre dentro de 24h após a última mensagem do
cliente; fora dessa janela (caso destas mensagens semanais de marketing) é obrigatório
usar templates aprovados pela Meta, que é exatamente o que este endpoint dispara.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field

from app import config
from app.messages import primeiro_nome
from app.schedule import Envio

URL_BOTMAKER = "https://api.botmaker.com/v2.0/notifications"
METODO = "POST"

# Nomes das variáveis de ambiente (os VALORES nunca aparecem no código).
VAR_TOKEN = "BOTMAKER_ACCESS_TOKEN"
VAR_CANAL = "BOTMAKER_CHANNEL_ID"
VAR_CAMPANHA = "BOTMAKER_CAMPAIGN"  # opcional

# O que gravamos no histórico no lugar do token real (veja `para_registro`).
TOKEN_OCULTO = f"<{VAR_TOKEN}>"


@dataclass
class Requisicao:
    """Uma requisição HTTP completa, pronta para ser enviada (mas não será)."""

    metodo: str
    url: str
    cabecalhos: dict[str, str] = field(repr=False)  # repr=False: não imprime o token em logs
    corpo: dict

    def para_registro(self) -> dict:
        """Versão SEGURA para gravar no banco: o token real é trocado por um marcador.

        O banco é um arquivo comum; gravar o token ali seria o mesmo que deixá-lo
        escrito no código. O marcador mostra QUAL variável seria usada.
        """
        cabecalhos = dict(self.cabecalhos)
        cabecalhos["access-token"] = TOKEN_OCULTO
        return {
            "metodo": self.metodo,
            "url": self.url,
            "cabecalhos": cabecalhos,
            "corpo": self.corpo,
        }

    def para_json(self) -> str:
        """JSON (legível, com acentos) da versão segura, para a coluna requisicao_json."""
        return json.dumps(self.para_registro(), ensure_ascii=False, indent=2)


def normalizar_telefone(telefone: str, codigo_pais_padrao: str | None = None) -> str:
    """Converte o telefone para o formato da Botmaker: SÓ DÍGITOS, com código do país.

    Exemplos:
        '+81 965-431-3024'  -> '819654313024'     (já tinha o código do país)
        '0055 11 95566-7788' -> '5511955667788'   (prefixo internacional 00)
        '(11) 95566-7788'   -> '5511955667788'    (sem DDI: usa o padrão, 55)
    """
    original = telefone.strip()
    digitos = re.sub(r"\D", "", original)  # \D = qualquer caractere que NÃO é dígito
    if not digitos:
        raise ValueError(f"Telefone inválido (sem dígitos): {telefone!r}")

    if original.startswith("+"):
        return digitos                # "+" indica que o código do país já está presente
    if original.startswith("00"):
        return digitos[2:]            # "00" é o prefixo de discagem internacional
    # Sem "+" nem "00": assumimos número nacional e acrescentamos o DDI padrão.
    # lstrip("0") remove o "0" de tronco ("011 9...") que não faz parte do número.
    return (codigo_pais_padrao or config.codigo_pais_padrao()) + digitos.lstrip("0")


def slug(texto: str) -> str:
    """'Público jovem' -> 'publico_jovem' (nome seguro para template/IDs)."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def montar_requisicao(envio: Envio) -> Requisicao:
    """Monta a requisição da Botmaker para UMA mensagem de UM cliente.

    Levanta:
        ConfigError  se BOTMAKER_ACCESS_TOKEN ou BOTMAKER_CHANNEL_ID não estiverem definidas;
        ValueError   se o telefone do cliente não tiver dígitos.
    """
    token = config.variavel_obrigatoria(VAR_TOKEN)      # lido do ambiente, não do código
    canal = config.variavel_obrigatoria(VAR_CANAL)
    campanha = os.getenv(VAR_CAMPANHA, "").strip() or None  # None vira null no JSON

    trilha_slug = slug(envio.trilha)
    data_iso = envio.data.isoformat()

    corpo = {
        "name": f"Trilha {envio.trilha} - mensagem {envio.numero_mensagem} - {data_iso}",
        "channelId": canal,
        "campaign": campanha,
        # Convenção deste projeto: um template/intent por mensagem, ex.:
        # 'trilha_alto_valor_msg_1'. Eles precisam existir (aprovados) na Botmaker.
        "intentIdOrName": f"trilha_{trilha_slug}_msg_{envio.numero_mensagem}",
        "contacts": [
            {
                "contactId": normalizar_telefone(envio.telefone),
                "variables": {
                    # {nome} do enunciado: o template pode usar `nome`...
                    "nome": primeiro_nome(envio.cliente_nome),
                    # ...e `mensagem` leva o texto final, já com {nome} substituído,
                    # para que a requisição gravada mostre exatamente o conteúdo.
                    "mensagem": envio.texto,
                },
                # Devolvido no webhook: permite relacionar o evento ao nosso registro.
                "webhookPayload": f"cliente-{envio.cliente_id}|{trilha_slug}|msg-{envio.numero_mensagem}|{data_iso}",
            }
        ],
    }
    cabecalhos = {
        "access-token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return Requisicao(metodo=METODO, url=URL_BOTMAKER, cabecalhos=cabecalhos, corpo=corpo)

"""
Cronograma: quando cada mensagem de cada cliente confirmado deve ser enviada.

Regras do enunciado e como foram implementadas:
  1. Cada trilha tem 3 mensagens, uma por semana, sempre no MESMO dia da semana
     (configurável em DIA_SEMANA_ENVIO).
  2. O cliente faz UMA trilha de cada vez, na ordem de prioridade: termina as 3
     semanas da primeira e só então começa a próxima.
  3. Só clientes CONFIRMADOS entram.

Decisões minhas (para o README/entrevista):
  - O primeiro envio é no primeiro dia de envio configurado NA data da confirmação ou
    depois dela (se confirmou numa segunda e o dia é segunda, o 1º envio é no mesmo dia).
  - O cronograma é uma FUNÇÃO PURA de (data de confirmação, trilhas, dia da semana).
    Não guardamos as datas no banco: calculamos sempre, então nunca ficam desatualizadas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.messages import MENSAGENS, renderizar_mensagem
from app.tracks import ordenar_por_prioridade


@dataclass(frozen=True)
class ClienteConfirmado:
    """Dados mínimos de um cliente confirmado para montar o cronograma."""

    id: int
    nome_completo: str
    telefone: str
    confirmado_em: date
    trilhas: tuple[str, ...]


@dataclass(frozen=True)
class Envio:
    """Uma mensagem prevista para um cliente numa data."""

    data: date
    cliente_id: int
    cliente_nome: str
    telefone: str
    trilha: str
    numero_mensagem: int   # 1, 2 ou 3 dentro da trilha
    texto: str             # já com {nome} substituído pelo primeiro nome


def proxima_data_do_dia(a_partir_de: date, dia_semana: int) -> date:
    """Primeira data cujo dia da semana é `dia_semana`, a partir de `a_partir_de` (inclusive).

    `date.weekday()` devolve 0=segunda ... 6=domingo. A conta `(alvo - atual) % 7`
    dá quantos dias faltam (0 se hoje já é o dia). O `%` do Python nunca devolve
    negativo, então funciona também quando o dia alvo "já passou" nesta semana.
    """
    faltam = (dia_semana - a_partir_de.weekday()) % 7
    return a_partir_de + timedelta(days=faltam)


def gerar_envios_do_cliente(cliente: ClienteConfirmado, dia_semana: int) -> list[Envio]:
    """Todos os envios de UM cliente, da primeira à última mensagem."""
    primeiro_envio = proxima_data_do_dia(cliente.confirmado_em, dia_semana)
    envios: list[Envio] = []
    semana = 0  # contador global de semanas: não reinicia ao trocar de trilha

    # Trilhas em ordem de prioridade; dentro de cada uma, as 3 mensagens em ordem.
    for trilha in ordenar_por_prioridade(cliente.trilhas):
        for numero, modelo in enumerate(MENSAGENS[trilha], start=1):
            envios.append(Envio(
                data=primeiro_envio + timedelta(weeks=semana),
                cliente_id=cliente.id,
                cliente_nome=cliente.nome_completo,
                telefone=cliente.telefone,
                trilha=trilha,
                numero_mensagem=numero,
                texto=renderizar_mensagem(modelo, cliente.nome_completo),
            ))
            # Ao somar 1 semana por mensagem, a 1ª mensagem da trilha seguinte cai
            # logo depois da 3ª da anterior => "uma trilha de cada vez".
            semana += 1
    return envios


def gerar_cronograma(clientes: list[ClienteConfirmado], dia_semana: int) -> list[Envio]:
    """Envios de todos os clientes confirmados, ordenados por data e depois por cliente."""
    todos: list[Envio] = []
    for cliente in clientes:
        todos.extend(gerar_envios_do_cliente(cliente, dia_semana))
    return sorted(todos, key=lambda e: (e.data, e.cliente_id, e.numero_mensagem))


def filtrar_periodo(envios: list[Envio], inicio: date, fim: date) -> list[Envio]:
    """Mantém só os envios com `inicio <= data <= fim`."""
    return [e for e in envios if inicio <= e.data <= fim]

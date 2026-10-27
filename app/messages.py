"""
Mensagens de cada trilha (texto do enunciado) e a substituição de {nome}.

São 3 mensagens por trilha, enviadas uma por semana, na ordem em que aparecem aqui.
"""
from __future__ import annotations

from app.tracks import ALTO_VALOR, GERAL, INCENTIVO, JOVEM, QUANTIDADE, TRILHAS

# Quantas mensagens cada trilha tem (e, portanto, quantas semanas ela dura).
QUANTIDADE_MENSAGENS = 3

MENSAGENS: dict[str, tuple[str, str, str]] = {
    ALTO_VALOR: (
        "Olá, {nome}! Você é um dos nossos clientes especiais: a partir desta semana, tem frete grátis em todos os pedidos.",
        "{nome}, separamos produtos que combinam com suas últimas compras. Confira no app.",
        "{nome}, queremos ouvir você: responda nossa pesquisa de 1 minuto e ganhe um cupom de 10%.",
    ),
    QUANTIDADE: (
        "Olá, {nome}! Pedidos acima de 20 itens têm 5% de desconto automático.",
        "{nome}, você pode agendar a entrega para o dia que preferir. Veja como no app.",
        "{nome}, monte sua lista de compras recorrentes e receba um lembrete na hora de repor.",
    ),
    INCENTIVO: (
        "Olá, {nome}! Use o cupom BEMVINDO e ganhe 15% na próxima compra.",
        "{nome}, temos produtos a partir de R$ 9,90 com entrega rápida. Aproveite para experimentar.",
        "{nome}, seu cupom de 15% expira em 7 dias. Não deixe passar!",
    ),
    JOVEM: (
        "E aí, {nome}! Siga a gente nas redes e veja os lançamentos antes de todo mundo.",
        "{nome}, indique um amigo e vocês dois ganham R$ 20 de desconto.",
        "{nome}, chegou a nova coleção. Dá uma olhada e conta pra gente o que achou.",
    ),
    GERAL: (
        "Olá, {nome}! Obrigado por comprar com a gente. Confira as novidades da semana.",
        "{nome}, ative as notificações do app para não perder nenhuma promoção.",
        "{nome}, conta pra gente como foi sua última compra respondendo uma pesquisa rápida.",
    ),
}

# Rede de segurança: se alguém editar este arquivo e esquecer uma trilha ou uma
# mensagem, o programa falha AO INICIAR (com mensagem clara) em vez de quebrar
# no meio de um envio.
assert set(MENSAGENS) == set(TRILHAS), "Toda trilha precisa ter mensagens."
assert all(len(m) == QUANTIDADE_MENSAGENS for m in MENSAGENS.values()), (
    f"Cada trilha precisa de exatamente {QUANTIDADE_MENSAGENS} mensagens."
)


def primeiro_nome(nome_completo: str) -> str:
    """'Emily Johnson' -> 'Emily'. (`split()` sem argumento ignora espaços extras.)"""
    partes = nome_completo.split()
    return partes[0] if partes else nome_completo


def renderizar_mensagem(modelo: str, nome_completo: str) -> str:
    """Troca o marcador {nome} pelo primeiro nome do cliente.

    Usamos `str.replace` e NÃO `str.format`: o `format` interpretaria qualquer
    outra chave `{...}` do texto e levantaria erro; o `replace` mexe só em {nome}.
    """
    return modelo.replace("{nome}", primeiro_nome(nome_completo))

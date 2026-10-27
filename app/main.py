"""
Aplicação web (FastAPI) — junta tudo: lista de clientes, decisão do analista,
cronograma e simulação de envios.

Como rodar:  uvicorn app.main:app --reload
Páginas:
    GET  /clientes                 lista de clientes, com filtro por trilha
    GET  /clientes/{id}            dados do cliente, trilhas sugeridas e motivos
    POST /clientes/{id}/confirmar  o analista confirma/ajusta as trilhas (grava no banco)
    GET  /cronograma               envios previstos nas próximas semanas + botão de simulação
    POST /simular-envios           "Simular envios de hoje": grava as requisições no histórico
    GET  /historico                requisições simuladas

As páginas são HTML gerado no servidor (templates Jinja2) e os formulários usam POST
simples: não há JavaScript, o que mantém o projeto fácil de ler e de explicar.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config, repositorio
from app.config import NOMES_DIAS_SEMANA, ConfigError
from app.db import conectar
from app.schedule import (
    ClienteConfirmado,
    filtrar_periodo,
    gerar_cronograma,
    gerar_envios_do_cliente,
)
from app.tracks import PRIORIDADE, TRILHAS, formatar_reais, ordenar_por_prioridade, sugerir_trilhas
from app.whatsapp import montar_requisicao

app = FastAPI(title="Trilhas de mensagens")

# Os templates ficam em app/templates. `Path(__file__).parent` é a pasta deste arquivo,
# então funciona em qualquer computador/Docker, independentemente de onde o comando rodou.
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ---------------------------------------------------------------------------
# "Relógio" do app. Fica numa função para os TESTES poderem trocar a data
# (monkeypatch em `agora`) sem depender do dia em que rodam.
# ---------------------------------------------------------------------------
def agora() -> datetime:
    return datetime.now()


def hoje() -> date:
    return agora().date()


# ---------------------------------------------------------------------------
# Filtros de formatação usados dentro dos templates ( {{ valor|reais }} ).
# ---------------------------------------------------------------------------
def _como_data(valor) -> date:
    """Aceita `date` ou texto ISO ('2026-10-26' / '2026-10-26T14:30:05')."""
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])


def filtro_data_br(valor) -> str:
    return _como_data(valor).strftime("%d/%m/%Y")


def filtro_dia_semana(valor) -> str:
    return NOMES_DIAS_SEMANA[_como_data(valor).weekday()]


def filtro_data_hora_br(valor: str) -> str:
    return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M")


def filtro_classe_trilha(trilha: str) -> str:
    """'Alto valor' -> 't1' (classe CSS com a cor da trilha)."""
    return f"t{PRIORIDADE[trilha]}"


templates.env.filters["reais"] = formatar_reais
templates.env.filters["data_br"] = filtro_data_br
templates.env.filters["dia_semana"] = filtro_dia_semana
templates.env.filters["data_hora_br"] = filtro_data_hora_br
templates.env.filters["classe_trilha"] = filtro_classe_trilha


def _pagina(request: Request, nome: str, contexto: dict, status_code: int = 200):
    """Atalho para renderizar um template (assinatura nova do Starlette: request primeiro)."""
    return templates.TemplateResponse(request, nome, contexto, status_code=status_code)


@app.exception_handler(ConfigError)
async def tratar_erro_de_configuracao(request: Request, erro: ConfigError):
    """Qualquer ConfigError (token ausente, dia da semana inválido...) vira uma página
    de erro amigável, em vez de um "Internal Server Error" sem explicação."""
    return _pagina(
        request, "erro.html",
        {"titulo": "Configuração incompleta", "mensagem": str(erro)},
        status_code=500,
    )


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@app.get("/")
def inicio():
    return RedirectResponse("/clientes")


@app.get("/clientes", response_class=HTMLResponse)
def listar_clientes(request: Request, trilha: Optional[str] = None):
    # Parâmetro vazio ("Todas") chega como "" -> tratamos como "sem filtro".
    if trilha and trilha not in TRILHAS:
        raise HTTPException(status_code=400, detail=f"Trilha desconhecida: {trilha!r}")

    with conectar() as conn:
        clientes = repositorio.listar_clientes(conn)
        confirmadas = repositorio.mapa_confirmacoes(conn)

    linhas = []
    for cliente in clientes:
        # As sugestões são CALCULADAS na hora (função pura) a partir dos dados do cliente:
        # assim nunca ficam desatualizadas em relação às regras.
        sugeridas = [
            s.trilha
            for s in sugerir_trilhas(
                cliente["idade"], cliente["valor_total_carrinhos"], cliente["quantidade_total_itens"]
            )
        ]
        # O filtro usa as trilhas SUGERIDAS: "mostre quem se encaixa nesta trilha".
        if trilha and trilha not in sugeridas:
            continue
        linhas.append({
            "cliente": cliente,
            "sugeridas": sugeridas,
            "confirmadas": confirmadas.get(cliente["id"]),  # None = ainda não confirmado
        })

    return _pagina(request, "clientes.html", {
        "pagina": "clientes",
        "linhas": linhas,
        "trilhas": TRILHAS,
        "trilha_filtro": trilha or "",
        "total_banco": len(clientes),
    })


def _contexto_cliente(conn, cliente_id: int, **extra) -> dict:
    """Reúne tudo que a página de um cliente precisa. Levanta 404 se o cliente não existe."""
    cliente = repositorio.buscar_cliente(conn, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    sugestoes = sugerir_trilhas(
        cliente["idade"], cliente["valor_total_carrinhos"], cliente["quantidade_total_itens"]
    )
    confirmacao = repositorio.buscar_confirmacao(conn, cliente_id)

    # Caixas marcadas no formulário: a decisão já gravada, se houver; senão as sugestões.
    if confirmacao:
        selecionadas = set(confirmacao[1])
    else:
        selecionadas = {s.trilha for s in sugestoes}

    envios = []
    if confirmacao:
        confirmado = ClienteConfirmado(
            id=cliente["id"], nome_completo=cliente["nome_completo"],
            telefone=cliente["telefone"], confirmado_em=confirmacao[0],
            trilhas=tuple(confirmacao[1]),
        )
        envios = gerar_envios_do_cliente(confirmado, config.dia_semana_envio())

    contexto = {
        "pagina": "clientes",
        "cliente": cliente,
        "sugestoes": sugestoes,
        "motivos": {s.trilha: s.motivo for s in sugestoes},
        "trilhas": TRILHAS,
        "selecionadas": selecionadas,
        "confirmacao": confirmacao,
        "envios": envios,
        "salvo": False,
        "erro": None,
    }
    contexto.update(extra)
    return contexto


@app.get("/clientes/{cliente_id}", response_class=HTMLResponse)
def pagina_cliente(request: Request, cliente_id: int, salvo: int = 0):
    with conectar() as conn:
        contexto = _contexto_cliente(conn, cliente_id, salvo=bool(salvo))
    return _pagina(request, "cliente.html", contexto)


@app.post("/clientes/{cliente_id}/confirmar")
def confirmar_cliente(
    request: Request,
    cliente_id: int,
    # Cada caixa marcada envia name="trilhas" value="<nome>". Sem nenhuma marcada, o
    # navegador não envia o campo e o valor chega como None.
    trilhas: Optional[list[str]] = Form(None),
):
    escolhidas = trilhas or []
    with conectar() as conn:
        # Validações do lado do servidor (o HTML pode ser adulterado):
        invalidas = [t for t in escolhidas if t not in TRILHAS]
        if invalidas or not escolhidas:
            erro = (
                f"Trilha desconhecida: {invalidas[0]!r}." if invalidas
                else "Marque pelo menos uma trilha para confirmar o cliente."
            )
            contexto = _contexto_cliente(conn, cliente_id, erro=erro)
            # Mantém marcado o que o analista tinha escolhido, para ele corrigir.
            contexto["selecionadas"] = set(escolhidas) & set(TRILHAS)
            return _pagina(request, "cliente.html", contexto, status_code=400)

        # Garante 404 se o cliente não existir (antes de tentar gravar).
        _contexto_cliente(conn, cliente_id)
        repositorio.confirmar_trilhas(conn, cliente_id, ordenar_por_prioridade(escolhidas), agora())

    # Padrão POST -> Redirect -> GET: se o analista apertar F5, o navegador repete o GET
    # (inofensivo) e não reenvia o formulário. 303 = "veja outra página usando GET".
    return RedirectResponse(f"/clientes/{cliente_id}?salvo=1", status_code=303)


def _envios_previstos(conn) -> list:
    """Cronograma completo de todos os clientes confirmados."""
    return gerar_cronograma(repositorio.listar_confirmados(conn), config.dia_semana_envio())


@app.get("/cronograma", response_class=HTMLResponse)
def pagina_cronograma(request: Request, semanas: int = Query(4, ge=1, le=26)):
    data_hoje = hoje()
    # `semanas` semanas a partir de hoje (inclusive): hoje .. hoje + 7*semanas - 1 dias.
    # Assim cada dia da semana aparece exatamente `semanas` vezes na janela.
    fim = data_hoje + timedelta(days=7 * semanas - 1)

    with conectar() as conn:
        todos = _envios_previstos(conn)
        simulados = repositorio.chaves_ja_simuladas(conn)

    janela = filtrar_periodo(todos, data_hoje, fim)

    # Agrupa por data mantendo a ordem (a lista já vem ordenada por data).
    grupos: dict[date, list] = {}
    for envio in janela:
        grupos.setdefault(envio.data, []).append(envio)

    return _pagina(request, "cronograma.html", {
        "pagina": "cronograma",
        "grupos": grupos,
        "semanas": semanas,
        "hoje": data_hoje,
        "dia_envio": NOMES_DIAS_SEMANA[config.dia_semana_envio()],
        "envios_hoje": len(grupos.get(data_hoje, [])),
        "simulados": simulados,
        "sem_confirmados": not todos,
    })


@app.post("/simular-envios")
def simular_envios():
    """Botão "Simular envios de hoje".

    Para cada mensagem prevista para HOJE monta a requisição da Botmaker (sem enviar)
    e grava no histórico. Não chama nenhuma API externa.
    """
    data_hoje = hoje()
    instante = agora()

    with conectar() as conn:
        do_dia = [e for e in _envios_previstos(conn) if e.data == data_hoje]

        # Monta TODAS as requisições antes de gravar qualquer coisa. Se faltar o token,
        # `montar_requisicao` levanta ConfigError já na primeira (tratado pelo handler
        # acima) e nada é gravado pela metade.
        prontas, falhas = [], 0
        for envio in do_dia:
            try:
                prontas.append((envio, montar_requisicao(envio)))
            except ValueError:
                # Problema só deste cliente (telefone sem dígitos): pula e conta,
                # para não impedir a simulação dos demais.
                falhas += 1

        novos = sum(
            repositorio.registrar_envio(conn, envio, requisicao.para_json(), instante)
            for envio, requisicao in prontas
        )

    repetidos = len(prontas) - novos
    return RedirectResponse(
        f"/historico?previstos={len(do_dia)}&novos={novos}&repetidos={repetidos}&falhas={falhas}",
        status_code=303,
    )


@app.get("/historico", response_class=HTMLResponse)
def pagina_historico(
    request: Request,
    previstos: Optional[int] = None,
    novos: Optional[int] = None,
    repetidos: Optional[int] = None,
    falhas: Optional[int] = None,
):
    with conectar() as conn:
        historico = repositorio.listar_historico(conn)
    return _pagina(request, "historico.html", {
        "pagina": "historico",
        "historico": historico,
        # Resumo da última simulação (só aparece quando vem da redirecionamento do botão).
        "resumo": None if previstos is None else {
            "previstos": previstos, "novos": novos or 0,
            "repetidos": repetidos or 0, "falhas": falhas or 0,
        },
    })

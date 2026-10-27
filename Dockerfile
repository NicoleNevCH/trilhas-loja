# Imagem oficial do Python, versão "slim" (menor, sem ferramentas que não usamos).
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE=1: não cria arquivos .pyc dentro da imagem.
# PYTHONUNBUFFERED=1: mostra os logs na hora (sem esperar o buffer encher).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Pasta de trabalho dentro do contêiner. Os caminhos relativos do projeto
# (data/raw, data/loja.db) passam a valer a partir daqui: /app/data/...
WORKDIR /app

# Copiamos SÓ o requirements.txt primeiro e instalamos as dependências. O Docker guarda
# cada passo em cache: enquanto o requirements.txt não mudar, mudar o código não
# reinstala tudo (build bem mais rápido).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Agora o código da aplicação.
COPY app ./app

# Boa prática de segurança: não rodar como root. Criamos um usuário comum, criamos a pasta
# data (onde ficam banco e JSONs) e entregamos a pasta /app a esse usuário.
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

# Documenta a porta usada (não publica nada sozinho; quem publica é o `docker run -p`).
EXPOSE 8000

# --host 0.0.0.0 é obrigatório no Docker: com o padrão (127.0.0.1) o servidor só
# aceitaria conexões de DENTRO do contêiner e o navegador não conseguiria acessá-lo.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Imagem do worker (backend docker). O BUILD usa rede (pip); a EXECUÇÃO não (--network none).
FROM python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN grep -i '^pymupdf==' requirements.lock > /tmp/req.txt && pip install -r /tmp/req.txt && pip install --no-deps . && rm /tmp/req.txt
USER 65534:65534

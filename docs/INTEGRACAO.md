# Integração com o repo real (higgs)

**Status:** pronto para virar branch/PR. **Não foi enviado**: não tenho a URL/acesso do repo real nem autorização
para publicar PDFs, dados ou PR em nome do responsável. Estas são as etapas, na ordem.

## 1. Mapeamento de módulos (extrator-enem → `src/higgs/ingestion/`)

| aqui | lá | ação |
|---|---|---|
| `layout.py` (ordem por colunas, mobiliário com registro, sub/sobrescrito, frações, figuras) | `layout.py` | substituir/estender; manter `normalize.py` se já existir |
| `segment.py` (marcadores+posição, grade de rótulos, figuras por geometria, alertas) | `segment.py` | substituir; alertas novos mapeiam em `issues` |
| `gabarito.py` (+ identidade caderno/ano/dia) | `gabarito.py` | substituir; manter nomes de `answer.*` |
| `sandbox.py` + `worker.py` (bwrap, rlimits, sonda, tar validado) | `sandbox.py`, `sandbox_os.py`, `worker.py` | **comparar antes**: o repo já tem isolamento macOS/Linux e testes de efeito negado — não removê-los; portar só o canal de saída validado e o tmpfs com teto |
| `records.py` | `records.py` | **não substituir**: usar o hash e o `question_id` do repo real; ver §2 |
| `store.py` | `store.py` | idem: o repo real já tem runs imutáveis e `review_stale`; portar só diferenças comprovadas |
| `pipeline.py` (validações §8, relatório, compare) | `pipeline.py`, `report.py` | fundir validações/relatório |
| `tests/` | `tests/ingestion/` | portar testes de referência; PDFs não são versionados |

## 2. Antes do PR (bloqueios)
1. **Hash:** rodar `content_hash` do repo real sobre os mesmos campos e comparar com `records.content_hash` daqui.
   Se divergirem, usar o do repo real no `build_record` (um adaptador de 1 função) — **não** migrar hashes.
2. **Conflito de ids:** `question_id` aqui = `q-<12 do SHA>-<nnn>` (igual ao briefing); confirmar.
3. **Licença PyMuPDF (AGPL)** decidida (`BRIEFING_REVISADO.md` #5).
4. Rodar `uv sync --frozen --extra ingestao` no repo real e `pytest tests/ingestion`; nenhuma regressão nos testes existentes.
5. Reexecutar v5 e candidato sobre os 2 cadernos e rodar `extrator-enem compare` (precisa converter a saída v5 ou reexecutar o candidato no layout do repo real).

## 3. Como entregar (quando houver acesso)
```bash
git remote add real <URL_DO_REPO>   # só com sua autorização
git fetch real && git checkout -b feat/extrator-geometrico real/main   # nunca direto na main
# portar arquivos conforme o mapeamento; PR curto por módulo (layout/segment → gabarito → sandbox → pipeline)
```
Cada PR com: antes/depois nos casos de referência, testes, CI verde (`ci.yml` incluído aqui) e a lista de limites de
`DECISOES_PENDENTES.md`. Sem PDFs/dados no PR.

# Formato de saída, identidade e versionamento

## Layout em disco (`--dados <raiz>`)

```text
<raiz>/
  quarentena/<sha256>.pdf            original preservado (somente leitura), nome = hash
  saida/
    sources/<source_id>/             source_id = SHA-256 completo do PDF
      manifest.json                  labels já vistos + lista de execuções (nome do arquivo é só metadado saneado)
      current.json                   {"run_id": ...}  — atualizado de forma atômica (os.replace + flock)
      runs/<run_id>/                 imutável; run_id = UTC + aleatório + -v<INGESTION_VERSION>
        questions/<question_id>.json
        assets/<hash>.png            recursos visuais da questão (recorte renderizado a 200 dpi)
        snapshots/<hash>.png         recortes de conferência (130 dpi) — separados dos recursos
        report.json  relatorio.md  conferencia.csv  omitted.json
        FALHOU.json                  só em execução que falhou (nada é publicado)
    reviews/<question_id>.json       vereditos humanos, cada um preso ao content_sha256 examinado
```

Nova execução nunca sobrescreve outra; execuções concorrentes não colidem (`mkdir exist_ok=False` + id aleatório).
Caminhos internos derivam de hashes; nomes recebidos nunca viram caminho.

## Registro por questão (`record_version = "2"`)

Superconjunto do registro v1 (briefing §7.2): todos os campos de v1 existem com o mesmo significado.

| campo | notas |
|---|---|
| `record_version` | `"2"` (v1 + `answer.state`, `regions`, `assets[].role/bbox`) |
| `question_id` | `q-<12 primeiros do SHA da fonte>-<nnn>` — compatível com v1 |
| `number`, `status` | `extracted` \| `needs_review`; `extracted` ≠ revisado por pessoa |
| `content_sha256` | hash canônico de enunciado, alternativas (+ `asset_ids`), tabelas e `answer` (letra, estado, origem) |
| `stem` | texto com `[[figura:<12 primeiros do hash>]]` na posição da figura |
| `choices[]` | `{letter, text, asset_ids}`; `asset_ids` = hash completo do recurso |
| `answer` | `{letter, state, origin, origin_label}`; `state` ∈ `found`/`annulled`/`not_provided`; `origin` = SHA-256 do gabarito |
| `location` | `{page_start, page_end}` (1-based) |
| `source` | `source_id` = `src-<12>`; `source_sha256` completo; `version`; `label` |
| `assets[]` | `{asset_id, hash, kind raster\|vector, page, bbox, role stem\|choice\|unassigned, letter?}` |
| `snapshots[]` | `{hash, page, bbox}` recortes da questão por (página, coluna) |
| `regions` | bbox do marcador de cada alternativa (rastreabilidade; ainda não há bbox por todo campo) |
| `issues[]` | `{code, severity critical\|review\|info, message}` |
| `annotations` | vazio na extração; nunca `reviewed` automático |
| `provenance` | versão da transformação, extrator, `run_id`, rótulo da fonte |
| `reprocessing` | `review_stale`, `stale_reviews`, `valid_review`, `changed_from_previous_run` |

**Identificadores:** `source_id` do diretório = SHA-256 completo; `source.source_id` no JSON = `src-<12>`.
`asset_ids` das alternativas = hash completo; referência textual `[[figura:…]]` = 12 primeiros — resolve por prefixo.
`answer.origin` = hash do gabarito, não o nome do arquivo.

## Convenção de matemática

Texto cru do PDF + marcação: sobrescrito `^{..}`, subscrito `_{..}` (por tamanho/posição/flag do glifo) e
fração `\frac{num}{den}` (reconstruída pela barra desenhada). **Fração reconstruída é geometria, não leitura
literal**: toda questão que a contém recebe `frac_reconstructed` (review). Não há garantia de LaTeX válido
para o conjunto; trechos não reconstruídos ficam como texto bruto e sinalizados (`fragmented_formula`).

## Estados do gabarito

`found` (número+caderno+ano validados), `annulled` (PDF diz "Anulado"), `not_provided` (questão ausente).
Estados *ambíguo* e *incompatível* (propostos no briefing §7.3) ainda não são emitidos: gabarito de outro
caderno/ano/dia é **recusado** na admissão (exit 4) em vez de associado.

## Hash e revisão

Revisão humana (`extrator-enem review`) grava o `content_sha256` examinado. Reprocessar com conteúdo diferente
marca `review_stale`; a aprovação antiga não vale para o hash novo. Nada automático cria `origin="reviewed"`.
Mudança que altere o conteúdo revisável (inclusive transcrição futura de OCR) entra no hash por construção.

## Propostas de contrato (não publicadas — combinar com curadoria/persistência)

Estado de gabarito ambíguo/incompatível; representação original×normalizada de matemática com bbox;
transcrição de figura (método/versão) separada de descrição inferida; prontidão visual×textual separadas.

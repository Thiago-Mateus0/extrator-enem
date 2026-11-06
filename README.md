# extrator-enem

CLI interna que transforma prova + gabarito oficiais do ENEM (PDF) em questões estruturadas (JSON),
preservando texto, expoentes/subscritos e frações (quando recuperáveis), com alertas explícitos
para tudo que não foi lido com fidelidade. Briefing original: `BRIEFING_DESENVOLVEDOR_EXTRATOR_ENEM.md`.

Escopo: ENEM 2º dia (caderno 5 amarelo), testado com 2024 e 2025, questões 91–180.
Não usa IA nem rede. Python ≥ 3.11 + PyMuPDF.

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[pdf,dev]'
# PDFs oficiais em dados/provas/ (não versionados; conferir SHA-256 no briefing §3)
.venv/bin/python -m extrator_enem.cli extract dados/provas/2024_PV_impresso_D2_CD5.pdf \
    --gabarito dados/provas/2024_GB_impresso_D2_CD5.pdf --de 91 --ate 180 --saida dados/saida/2024
.venv/bin/pytest -q
```

Saída em `--saida`: `questions.json`, `report.json`, `relatorio.md`, `omitted.json`.
Faixa de questões (`--de/--ate`) é parâmetro: a regra 91–135 / 136–180 é do perfil desses cadernos.

## Resultado atual (leitura nativa, sem IA, parser em sandbox)

| | 2024 | 2025 |
|---|---|---|
| Questões encontradas | 90/90 | 90/90 |
| Para conferir (alertas) | 16 | 12 |
| Gabarito: letra / anulada | 89 / 1 | 87 / 3 |
| Tempo (extração completa) | ~8 s | ~8 s |

Dos 16 defeitos com veredito humano do briefing: o **deslocamento de gráficos da 2025 Q129 está corrigido**
(cada gráfico ligado à sua letra, por geometria) e 14 são sinalizados; 2024 Q142 (número misto) e as setas da
Q94 seguem sem recuperação (`xfail` estrito). Sinalizar **não é corrigir**; contagens não medem fidelidade.

## Comandos

```bash
extrator-enem extract PROVA.pdf --gabarito GAB.pdf --de 91 --ate 180 --dados dados/ensaio/2024 [--ano --dia --caderno]
extrator-enem sonda                 # prova funcional do isolamento
extrator-enem compare RUN_A RUN_B   # baseline x candidato: corrigidos/mantidos/introduzidos/conteúdo alterado
extrator-enem review --dados D --source SHA --numero 130 --verdict approved --by NOME   # humano; preso ao hash
```

Códigos de saída: 0 ok · 1 erro · 2 extração INCOMPLETA · 3 isolamento indisponível (falha fechada) · 4 identidade da fonte.

## Convenções, formato e identidade

Ver `docs/FORMATO.md` (layout em disco, campos, hashes, gabarito, revisão) e
`docs/DECISOES_PENDENTES.md` (decisões em aberto, licença AGPL do PyMuPDF, limites).

- Tabelas com linhas desenhadas viram `tables[]` (células por recorte, vírgulas decimais preservadas) + recorte `kind=table`; o cabeçalho é a 1ª linha por *inferência* (`header_inferred`). Tabelas sem filetes não são detectadas.
- Sobrescrito `^{..}`, subscrito `_{..}`, fração `\frac{num}{den}`; toda fração reconstruída tem alerta `frac_reconstructed`.
- Alternativa só em figura: texto vazio + `choice_image_only` (info) + `asset_ids` da figura da mesma altura do rótulo.
- Gabarito: `found` / `annulled` / `not_provided`; outro caderno/ano/dia é recusado. Nunca se infere resposta.
- Parser roda em `bwrap` (rede/home negados, raiz somente leitura, sem credenciais, rlimits CPU/mem/arquivo/tempo/volume);
  se o isolamento ou a sonda falhar, **nada roda**.

## Alertas (`issues[].code`)

| código | severidade | significado |
|---|---|---|
| `choices_not_found`, `empty_stem`, `empty_choice` | critical | estrutura não recuperada |
| `fragmented_formula`, `broken_glyph`, `duplicate_choices`, `answer_without_choice` | critical | texto de fórmula/alternativa não confiável |
| `frac_reconstructed`, `missing_reaction_arrow`, `asset_unassigned`, `answer_not_provided` | review | recuperação geométrica / possível perda / figura sem dono / sem gabarito |
| `choice_image_only` | info | alternativa existe só como imagem/vetor |

`status` = `needs_review` se houver alerta que não seja `info`; `extracted` **não** significa revisado.

## Ainda não implementado

- OCR/visão (adiado por decisão do responsável; ver `docs/DECISOES_PENDENTES.md`).
- Bbox para todos os campos; estados de gabarito ambíguo/incompatível; transcrição de texto dentro de figuras.
- Comparação com a baseline v5 (não estava disponível).

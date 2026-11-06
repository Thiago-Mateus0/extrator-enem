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

## Resultado atual (leitura nativa, sem IA)

| | 2024 | 2025 |
|---|---|---|
| Questões encontradas | 90/90 | 90/90 |
| Para conferir (alertas) | 16 | 12 |
| Gabarito: letra / anulada | 89 / 1 | 87 / 3 |

Dos 16 defeitos com veredito humano do briefing, **14 são sinalizados** e 2 passam em silêncio
(2024 Q142 número misto; 2025 Q129 deslocamento de gráficos) — ambos têm teste `xfail` estrito.
Sinalizar **não é corrigir**: contagens de alerta não medem fidelidade.

## Convenções do texto

- Sobrescrito `^{..}`, subscrito `_{..}`, fração `\frac{num}{den}` (LaTeX-like).
- Fração é reconstruída pela geometria (barra + texto acima/abaixo): toda questão com `\frac`
  recebe o alerta `frac_reconstructed` e **deve ser conferida contra a página**.
- Alternativa só em figura: texto vazio + alerta informativo `choice_image_only`.

## Estados do gabarito

`found` (letra), `annulled` (PDF diz "Anulado"), `not_provided` (questão ausente no gabarito).
Nunca se infere resposta resolvendo a questão.

## Alertas (`issues[].code`)

| código | severidade | significado |
|---|---|---|
| `choices_not_found`, `empty_stem`, `empty_choice` | critical | estrutura não recuperada |
| `fragmented_formula`, `broken_glyph`, `duplicate_choices`, `answer_without_choice` | critical | texto de fórmula/alternativa não confiável |
| `frac_reconstructed`, `missing_reaction_arrow` | review | recuperação geométrica / seta de reação provavelmente ausente |
| `choice_image_only` | info | alternativa existe só como imagem/vetor |

`status` = `needs_review` se houver alerta que não seja `info`; `extracted` **não** significa revisado.

## Limites conhecidos (não implementado)

- Sem extração de figuras/recursos, manifesto de assets nem recortes (snapshots) — portanto o vínculo
  figura↔alternativa (ex.: 2025 Q129) não é verificado.
- Sem OCR/visão: fórmulas que o PDF não traz como texto/geometria (setas ⇌ vetoriais, números mistos
  sem barra, fatoriais) ficam sinalizadas ou, nos 2 casos acima, silenciosas.
- Sem sandbox/isolamento do parser, sem `source_id`/hash de revisão/reprocessamento imutável do briefing §7–9.
- Heurísticas de detecção podem gerar falsos alarmes; só conferência contra o PDF confirma.

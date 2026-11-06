# Decisões pendentes, limites e licença

## Precisam do responsável do projeto
1. **OCR/visão externo** (modelo/fornecedor, teto de custo, autorização para enviar regiões a serviço externo).
   Adiado por decisão do responsável; nada do pipeline chama serviço externo (`chamadas_externas: 0`).
   A etapa 4 do pipeline (recuperação de regiões difíceis) é o ponto de encaixe; ver "Candidatas" abaixo.
2. **Licença do PyMuPDF**: AGPL-3.0 (ou comercial da Artifex). Hoje é dependência opcional `[pdf]` de ferramenta
   interna; confirmar se a distribuição pretendida é compatível ou se precisa de licença comercial / outro parser.
3. **Metas de melhoria** com conjunto e denominador explícitos (briefing §12): não há meta numérica aprovada.
4. **Contrato final do dataset** (estados de gabarito, matemática original×normalizada): combinar com curadoria.
5. **Baseline v5 / referência humana**: as execuções v5 e o código `higgs.ingestion` não estavam disponíveis; por isso
   não há comparação baseline×candidato por caso. `extrator-enem compare` já compara duas execuções deste extrator.

## Candidatas para OCR/visão (fila, sem execução)
Casos que a leitura nativa não resolve: setas de equilíbrio vetoriais (2024 Q94, 2025 Q123), números mistos sem barra
(2024 Q142), frações com texto residual (2024 Q149 B/D, Q141 com `d(Q)/d(R)` parcial), fatoriais (2024 Q139),
equações em alternativas (2025 Q159/Q164), símbolo vetorial (2024 Q104).

## Limites conhecidos
- Fidelidade **não medida** sem referência: contagens de alerta não são taxa de acerto.
- 2 casos de referência conhecidos passam sem alerta ou com leitura errada: 2024 Q142 (xfail) e setas da Q94 (xfail).
- Heurísticas (fragmentação, seta ausente) podem dar falso alarme ou falso negativo; só conferência contra o PDF confirma.
- Perfil só ENEM D2 caderno 5 (2024/2025) testado; faixa 91–180 é parâmetro.
- Sandbox: **Linux+bwrap** e **Docker** (macOS/Windows/Linux) implementados; ambos com a mesma sonda. Testado de fato: Linux (bwrap e docker). **macOS/Windows com Docker Desktop: não testado por mim** — rodar `extrator-enem sonda` lá é o primeiro teste. Sem nenhum dos dois, a ferramenta recusa (falha fechada). Licença do Docker Desktop (empresas grandes) é decisão do responsável; Colima/Podman são alternativas livres.
- Sem `bbox` por campo (só `regions` dos marcadores e `assets`/`snapshots`); proposta de manifesto de regiões pendente.
- Referências textuais de recursos usam prefixo de 12 hex; colisão improvável mas não tratada.

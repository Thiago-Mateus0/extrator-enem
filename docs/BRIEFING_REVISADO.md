# Briefing revisado — o que mudar na task original e por quê

Base: o que a implementação em `extrator-enem` mostrou sobre os PDFs reais (ENEM 2024/2025 D2 cad. 5).
Cada recomendação traz a evidência. Nada aqui altera critérios de honestidade do briefing (não inventar gabarito,
não aprovar por IA, não declarar 100%).

## 1. Mudanças recomendadas

| # | Mudança | Evidência / motivo |
|---|---|---|
| 1 | **Inverter a ordem do plano: geometria nativa primeiro, OCR/visão só para o resíduo.** O Marco B vira "esgotar o que o PDF já contém" e o OCR passa a Marco B2, condicionado a uma lista de resíduo. | Sem IA e sem custo, a leitura por posição trouxe 90/90 questões, figuras ligadas à letra certa (corrigiu 2025 Q129), expoentes/subscritos (`2^{20}`, `M_{1}`) e frações com barra. O que sobra é pequeno e enumerável (`DECISOES_PENDENTES.md`). Contratar OCR antes disso seria pagar por problema já resolvido. |
| 2 | **Reduzir o escopo da fidelidade crítica a "casos com resíduo" + lote de aceitação.** Meta numérica só depois do baseline v5 reexecutado no mesmo conjunto. | Hoje só medimos *alertas*, não fidelidade. Os 16 casos têm descrição do defeito, não valor esperado; transformá-los em campos-ouro (ex.: alternativa C da Q141) é o trabalho humano de maior retorno. |
| 3 | **Não manter dois extratores.** A entrega deve entrar como PR/branch no repo real, substituindo `layout.py`/`segment.py` e acrescentando `assets`/`sandbox`, não como repo paralelo. | O próprio §13 proíbe duas implementações divergentes. Mapeamento e passos em `docs/INTEGRACAO.md`. |
| 4 | **Congelar a identidade do hash antes de integrar.** Reusar o `records.py`/`content_sha256` do repo real, ou entregar adaptador testado. | O hash deste repo (`records.content_hash`) tem canonicalização própria e **não é** o do repo real; trocar sem migração invalidaria revisões (§8). Item aberto. |
| 5 | **Decidir a licença do PyMuPDF (AGPL-3.0) agora, não no fim.** | É dependência obrigatória do caminho feliz. Se a distribuição pretendida não aceita AGPL, a escolha de parser muda a arquitetura, não só a dependência. |
| 6 | **Trocar "estado do gabarito" por contrato mínimo já implementado** (`found/annulled/not_provided`; outro caderno/ano/dia é *recusado* na admissão) e deixar `ambíguo/incompatível` para quando houver caso real. | O PDF oficial diz "Anulado" literalmente, então anulado≠vazio é resolvível sem inventar estados. Estados sem caso real são contrato sem uso. |
| 7 | **Exigir verificação do diagnóstico da Q94 antes de tratá-la como defeito de tabela.** | A leitura nativa preserva as vírgulas (9,5; 11,0; 7,7…); o que falta são as setas (vetores). O defeito de tabela registrado pode ser da v5, não do PDF — conferir contra a v5 antes de gastar esforço. |
| 8 | **Sandbox: declarar só Linux+bwrap como suportado e deixar macOS fora do primeiro marco.** | Falha fechada já implementada e testada em Linux; macOS exigiria `sandbox-exec` com perfil próprio e testes — trabalho separado, sem ganho para o piloto. |
| 9 | **Critério de aceite 95/100 de revisão de código mantido, mas separado de métricas de fidelidade** (já dito no briefing; reforçar no relatório). | Evita o risco de a nota de código ser lida como acerto de extração. |

## 2. Marcos revisados

- **A (feito):** baseline reproduzido sobre os 4 PDFs com hash conferido; inventário de defeitos; arquitetura; contrato v2 superconjunto do v1.
- **B1 (feito, esta entrega):** segmentação por posição, figuras↔alternativas por geometria, expoentes/frações, gabarito com estados, sandbox, runs imutáveis, hash/revisão.
- **B2 (depende de decisão):** resíduo → OCR/visão com fornecedor/teto definidos; ver lista em `DECISOES_PENDENTES.md`.
- **C:** integração no repo real (`docs/INTEGRACAO.md`), baseline v5 × candidato por caso, lote de aceitação separado, relatório com denominadores.

## 3. O que deve ser decidido por pessoas (não por mim)
Licença do PyMuPDF · fornecedor/teto de OCR · quais campos-ouro adjudicar (e quem) · lote de aceitação (12 questões sorteadas, sugestão minha) · política de migração de hash.

# extrator-enem

Lê a prova e o gabarito oficiais do ENEM (PDF) e entrega cada questão em JSON: enunciado, alternativas, figuras, tabelas, fórmulas e resposta certa. É a peça de extração da plataforma de estudos que o Thiago faz com um colega e sócio; este repositório é só o extrator, isolado e testável. Integração com a plataforma: `docs/INTEGRACAO.md`.

Python 3.11+ com PyMuPDF. **Não usa IA nem internet.**

Pessoa: **Thiago** (dono do extrator; decide o que entra e o que vai para a plataforma).

---

## Regras invioláveis

1. **Não errar em silêncio.** O que o programa não tem certeza de ter lido direito vira **alerta**, nunca passa batido. Heurística nova sem alerta correspondente não entra.
2. **Sinalizar não é corrigir.** Contagem de alertas não é taxa de acerto. Não escreva "fidelidade de X%" em doc, PR ou relatório sem campo-ouro que sustente.
3. **`extracted` não quer dizer revisado.** Questão com qualquer alerta que não seja `info` fica `needs_review`.
4. **Nunca inventar resposta.** Sem gabarito, a questão sai `not_provided`.
5. **Isolamento falha fechado.** O parser abre PDF que não controlamos: roda sem rede, sem acesso à pasta pessoal, sem credenciais e com limites de memória, tempo e saída. Se a caixa não monta ou a sonda reprova, **nada roda**. Nunca contorne, nunca adicione modo "sem sandbox".
6. **Sem chamada externa.** Nada do pipeline chama serviço externo (OCR, visão, API). Isso só muda com decisão do Thiago.
7. **PDFs oficiais e dados de execução nunca entram no git** (`dados/` é ignorado). Testes usam o PDF sintético que o próprio teste gera.
8. **Cada questão guarda de onde veio** (hash do PDF, página, recorte da imagem). Não quebre a rastreabilidade.
9. **Número vem da execução, nunca do texto.** Contagens (questões encontradas, `needs_review`, itens-ouro) saem do `relatorio.md` / `report.json` na hora. Não copie número para doc, PR ou teste.
10. **Revisão presa ao conteúdo.** Se o texto da questão muda numa nova extração, a revisão vira vencida. Não mude esse comportamento sem teste.

---

## Onde está o quê

```
src/extrator_enem/   ← cli, pipeline, layout, segment, gabarito, sandbox, worker, records, store, ouro
tests/               ← pytest; test_sintetico gera PDF pequeno e roda o parser de verdade
tests/gold/ouro.json ← campos-ouro: valores esperados lidos no PDF (ainda sem conferência humana)
docs/FORMATO.md      ← o que tem em cada JSON, como os hashes são calculados
docs/DECISOES_PENDENTES.md  ← o que ainda precisa de decisão do Thiago
docs/INTEGRACAO.md   ← como levar para o repositório da plataforma
docs/exemplo/        ← registro de exemplo; o teste sintético confere que continua igual à saída real
dados/               ← PDFs oficiais e saída de execuções. Ignorado pelo git.
```

**Antes de mexer numa área:** leia `docs/FORMATO.md` (se toca o JSON) ou `docs/DECISOES_PENDENTES.md` (se toca algo listado lá).

---

## Comandos

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
extrator-enem sonda                  # confere o isolamento nesta máquina (falha = nada roda)
pytest -q                            # testes com PDF real se pulam sem dados/provas
extrator-enem extract dados/provas/<PROVA>.pdf --gabarito dados/provas/<GABARITO>.pdf \
    --de 91 --ate 180 --dados dados/ensaio/<ano>
extrator-enem compare RUN_A RUN_B    # o que mudou entre duas extrações
extrator-enem ouro --ouro tests/gold/ouro.json --run <ano>=<pasta da execução>
EXTRATOR_SANDBOX=docker pytest -q tests/test_sandbox.py   # força o backend Docker
```

Códigos de saída: 0 ok · 1 erro · 2 extração incompleta · 3 isolamento indisponível · 4 gabarito de outra prova.

Sem os PDFs oficiais em `dados/provas/`, só rodam os testes sintéticos. Isso é esperado, não é falha.

---

## Estilo de trabalho

- **Teste antes** no que for segmentação, alerta ou gabarito. Bug real vira teste; defeito conhecido que ainda não tem correção fica como falha esperada (`xfail`), não apagado.
- **Mudou extração? Compare.** Rode `extrator-enem compare` entre a execução antes e depois e diga o que mudou na PR.
- **Uma coisa por vez, sem parar à toa.** Se a tarefa cresceu além do combinado, registre o desvio na PR e siga; só pare se cair na **lista de parada** (seção Autonomia).
- **Não refatore o que não foi pedido.** Diff mínimo.
- Sem dependência nova sem justificar em uma linha. A licença do PyMuPDF (AGPL) é decisão pendente: não adicione dependência com licença restritiva.
- **O diff mora na PR, não no chat.** Toda PR traz **"O que conferir"**: até 3 linhas que o Thiago valida sem ler código (um comando, um comportamento).

---

## Autonomia

O Claude vai até a PR sozinho quando `pytest -q` passa e a CI está verde, em: correção de bug com teste, refatoração sem mudança de saída, novo alerta com teste, teste, script e documentação.

**Lista de parada — a única.** Nestes casos abre a PR e **não pede o merge**, esperando o Thiago:
- chamada a serviço externo, OCR ou visão (regra 6) ou qualquer dependência nova com impacto de licença;
- mudança no contrato do JSON (`docs/FORMATO.md`) ou na forma de calcular hashes;
- enfraquecer ou contornar o isolamento (regra 5);
- publicar algo na plataforma, ou levar PDF oficial ou dado de execução para o git;
- meta numérica de melhoria ou valor novo em `tests/gold/ouro.json` (precisa de conferência humana).

**Fora da lista, não pare para perguntar.** Escolha a opção mais reversível, registre a suposição na PR e siga até o fim da tarefa.

**Dentro da lista, parar o merge não é parar a sessão.** Registre a decisão em `docs/DECISOES_PENDENTES.md` com as opções e a recomendação; siga com o que não depende dela.

**Formato de resposta:** (1) o que mudou, 1–3 linhas · (2) link da PR · (3) testes · (4) o que precisa do Thiago, só se existir. Português, direto.

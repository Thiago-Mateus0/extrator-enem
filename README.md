# extrator-enem

Lê a prova e o gabarito oficiais do ENEM (PDF) e entrega cada questão em JSON: enunciado, alternativas,
figuras, tabelas, fórmulas e a resposta certa. O que o programa não tem certeza de ter lido direito
vira um **alerta**, em vez de passar batido.

Foi feito e testado com o 2º dia (caderno 5, amarelo), questões 91–180, das provas de 2024 e 2025.
Não usa IA nem internet. É Python 3.11+ com PyMuPDF. O briefing original está em
`BRIEFING_DESENVOLVEDOR_EXTRATOR_ENEM.md`.

## Como rodar

Você precisa dos PDFs oficiais em `dados/provas/`. Eles não vão para o git, de propósito.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

extrator-enem sonda        # confere se o isolamento funciona nesta máquina
extrator-enem extract dados/provas/2024_PV_impresso_D2_CD5.pdf \
    --gabarito dados/provas/2024_GB_impresso_D2_CD5.pdf \
    --de 91 --ate 180 --dados dados/ensaio/2024
```

Se o nome do arquivo não tiver ano, dia e caderno, passe `--ano 2024 --dia 2 --caderno 5`.

Cada execução cria uma pasta nova dentro de `--dados`, com:
`questions/` (um JSON por questão), `relatorio.md` (resumo para ler), `conferencia.csv`,
`report.json`, `assets/` e `snapshots/` (as figuras e o recorte de cada questão).

## Por que o isolamento

O parser abre PDFs que não controlamos, então ele roda numa caixa fechada: sem rede, sem acesso à sua
pasta pessoal, sem credenciais e com limites de memória, tempo e tamanho de saída. Se a caixa não
puder ser montada ou a sonda reprovar, **nada roda**.

| Sistema | Como isola | Precisa de |
|---|---|---|
| Linux | `bwrap` | `sudo apt install bubblewrap` |
| macOS, Windows, Linux | Docker | Docker Desktop, Colima ou Podman |

A escolha é automática (`bwrap` se existir, senão Docker). Para forçar: `EXTRATOR_SANDBOX=docker`.
Na primeira vez com Docker, ele monta a imagem (precisa de internet só nessa etapa, uns 150 MB).

Testei no Linux, com os dois backends, e a mesma prova deu resultado idêntico. **macOS e Windows ainda
não foram testados.** O `extrator-enem sonda` é o primeiro teste nessas máquinas.

## Resultado atual

| | 2024 | 2025 |
|---|---|---|
| Questões encontradas | 90 de 90 | 90 de 90 |
| Marcadas para conferir | 9 | 6 |
| Gabarito: letra / anulada | 89 / 1 | 87 / 3 |
| Tempo | ~20 s | ~20 s |

Dos 16 defeitos conhecidos do briefing: 1 foi corrigido (gráficos da 2025 Q129), 14 são sinalizados e 1
passa sem alerta (o número misto da 2024 Q142). Na Q94 o alerta existe, mas a seta de equilíbrio continua
sem ser recuperada. Esses dois casos estão nos testes como falha esperada. Sinalizar **não é corrigir**,
e estes números não medem fidelidade.

Números conferidos em 06/11/2026 numa extração nova, no Linux: 2024 teve 9 questões `needs_review`
e 2025 teve 6, e as 90 questões de cada prova foram encontradas.

## Os alertas

| Gravidade | Códigos | Quer dizer |
|---|---|---|
| critical | `choices_not_found`, `empty_stem`, `empty_choice`, `fragmented_formula`, `broken_glyph`, `duplicate_choices`, `answer_without_choice` | a estrutura ou o texto não é confiável |
| review | `frac_reconstructed`, `missing_reaction_arrow`, `asset_unassigned`, `answer_not_provided` | uma pessoa precisa olhar |
| info | `choice_image_only` | a alternativa existe só como imagem |

Questão com qualquer alerta que não seja `info` fica como `needs_review`. `extracted` **não** quer dizer revisado.

## Medir fidelidade (campos-ouro)

Os alertas dizem "olhe aqui"; os campos-ouro dizem se o texto extraído **é** o da prova.
`tests/gold/ouro.json` lista valores esperados (alternativas, trechos do enunciado, tabelas) lidos no PDF.

```bash
extrator-enem ouro --ouro tests/gold/ouro.json --run 2024=<pasta da execução> --run 2025=<pasta da execução>
```

Hoje são 32 itens: 18 certos e 14 errados, e os 14 são os defeitos já conhecidos (Q139, Q141, Q149, Q142
e a seta da Q94). Isso **não é a taxa de acerto do sistema**: o ouro foi montado em cima dos casos
problemáticos, então a taxa é pessimista. Os valores foram lidos por adjudicação automatizada e **ainda
precisam de conferência humana** antes de virarem meta.

## Outros comandos

```bash
extrator-enem compare RUN_A RUN_B     # o que mudou entre duas extrações
extrator-enem review --dados D --source SHA --numero 130 --verdict approved --by NOME
```

A revisão fica presa ao conteúdo da questão: se o texto mudar numa nova extração, ela é marcada como vencida.

Códigos de saída: 0 ok · 1 erro · 2 extração incompleta · 3 isolamento indisponível · 4 gabarito de outra prova.

## Limites

- Só lê o texto que está no PDF. Setas desenhadas, números mistos e algumas frações escapam.
- Tabelas só são detectadas se tiverem linhas desenhadas, e o cabeçalho é a primeira linha por inferência.
- Nunca inventa resposta: sem gabarito, a questão sai como `not_provided`.
- OCR e visão computacional ficaram para depois, por decisão do responsável.

## Para ler a seguir

- `docs/FORMATO.md`: o que tem em cada JSON, como os hashes são calculados.
- `docs/DECISOES_PENDENTES.md`: o que ainda precisa de decisão, incluindo a licença AGPL do PyMuPDF.
- `docs/INTEGRACAO.md`: como levar isto para o repositório do projeto real.

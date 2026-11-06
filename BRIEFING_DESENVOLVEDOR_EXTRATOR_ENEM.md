# Desenvolvimento do extrator de provas ENEM — briefing técnico

Data: 06/11/2026. Destinatário: desenvolvedor dedicado à extração de provas da Higgs AI.

**Objetivo:** entregar uma ferramenta interna que transforme prova e gabarito oficiais em questões estruturadas, preservando conteúdo, fórmulas, tabelas, imagens e proveniência, com erros e incertezas explícitos. O principal ganho esperado é reduzir o trabalho manual necessário para preparar o acervo.

**Estado deste documento:** passagem técnica solicitada pelo responsável do projeto. Os fatos sobre a implementação e os defeitos abaixo foram examinados no código/artefatos existentes. A arquitetura de evolução, as etapas de entrega e os critérios específicos propostos aqui são um plano de execução para alinhamento; não representam uma implementação pronta, escolha automática de fornecedor ou nova numeração no backlog.

## 1. Contexto e fronteira da sua entrega

A Higgs ajuda professores e escolas a preparar questões e simulados de Matemática, Física, Química e Biologia, incluindo interdisciplinaridade do segundo dia do ENEM. A engine usa o acervo para recuperar exemplos de questões e, futuramente, conhecimento de materiais didáticos.

A extração é uma **ferramenta interna de preparo de dados, fora do produto**. O professor não envia PDFs para o produto. Quem opera a ferramenta é a equipe que prepara o acervo. A engine de produção consumirá um dataset curado e versionado, não o PDF original nem diretamente o JSON intermediário da extração.

```text
Prova PDF + gabarito PDF do mesmo caderno
        ↓
Identificação, validação e preservação dos originais
        ↓
Extração de layout/texto/recursos + OCR/visão quando necessário
        ↓
Questões estruturadas + imagens + localização + alertas
        ↓
Validação automática e conferência dirigida dos casos problemáticos
        ↓
Curadoria/exportação do dataset — outra fronteira
        ↓
Carga e RAG da engine — outras fronteiras
```

Sua entrega termina na extração utilizável e na evidência da sua fidelidade. Não inclui construir a plataforma Go, banco PostgreSQL, geração de questões, busca vetorial, simulados, autenticação, publicação do dataset ou painel completo de curadoria.

Não transforme material didático em questão artificial nem gere respostas/resoluções que não existem na fonte. Livros e apostilas são expansão posterior, com representação por blocos/seções própria.

## 2. O que já existe e como começar

Já há um extrator executável em Python. Você não precisa reconstruir toda a infraestrutura para começar. Primeiro reproduza a versão atual, entenda seus resultados e proponha quais partes aproveitar, corrigir ou substituir.

| Caminho no repositório | Responsabilidade atual |
|---|---|
| `src/higgs/ingestion/cli.py` | CLI de extração e importação da conferência humana |
| `quarantine.py` | Validação inicial, limites, hash e preservação do original |
| `worker.py` | Parser de PDF e renderização executados em processo isolado |
| `sandbox.py`, `sandbox_os.py` | Limites e isolamento macOS/Linux |
| `layout.py` | Ordem de leitura, colunas e remoção controlada de cabeçalhos/rodapés/marcas-d'água |
| `normalize.py` | Normalização textual conservadora |
| `segment.py` | Segmentação de questões/alternativas e detecção de defeitos |
| `gabarito.py` | Leitura e associação do gabarito |
| `models.py` | Estruturas intermediárias e versão da transformação |
| `records.py` | Construção do JSON por questão e identidade/hash do conteúdo |
| `store.py` | Execuções imutáveis, ponteiro vigente e revisões ligadas ao hash |
| `report.py`, `conferencia.py` | Relatório, CSV e importação dos vereditos humanos |
| `classify.py` | Classificação opcional; separada da fidelidade da extração |
| `tests/ingestion/` | Testes existentes de layout, segmentação, reprocessamento, conferência e isolamento |

Os nomes depois da primeira linha da tabela pertencem a `src/higgs/ingestion/`.

Versões atuais: `INGESTION_VERSION = "5"` e `RECORD_VERSION = "1"`. A implementação usa PyMuPDF em um worker isolado; não há OCR geral nem transcrição completa do texto dentro de figuras.

Ambiente do projeto: Python 3.11–3.13, `uv`, `pyproject.toml` e `uv.lock`. Reproduza com as versões do lockfile antes de comparar alternativas. O backend da plataforma será Go, mas isso não obriga a reescrever o extrator em Go. Python é a base existente; uma mudança de linguagem precisa justificar integração, distribuição e testes.

### Comandos existentes

Execute na raiz do checkout disponibilizado para você:

```bash
uv sync --frozen --extra ingestao --python 3.11

uv run python -m higgs.ingestion.cli extract \
  dados/provas/2024_PV_impresso_D2_CD5.pdf \
  --gabarito dados/provas/2024_GB_impresso_D2_CD5.pdf \
  --de 91 --ate 180 --dados dados/ensaio-extrator/2024

uv run python -m higgs.ingestion.cli extract \
  dados/provas/2025_PV_impresso_D2_CD5.pdf \
  --gabarito dados/provas/2025_GB_impresso_D2_CD5.pdf \
  --de 91 --ate 180 --dados dados/ensaio-extrator/2025

uv run pytest -q tests/ingestion
uv run python -m higgs.ingestion.sandbox_os
```

As pastas de ensaio são novas: preserve as execuções de referência. Não use `--classificar` para medir extração; classificação é outro experimento e pode envolver modelo pago.

Os PDFs e os JSONs reais **não estão versionados no Git**. O responsável deve disponibilizá-los junto do acesso ao código. Não suponha que clonar o repositório traz o acervo. Não use caminhos pessoais da máquina do autor na implementação.

## 3. Acervo inicial e linha de base

Primeiro alvo: **ENEM 2024 e 2025, segundo dia, caderno 5 amarelo**, questões 91–180. São 90 por prova, 180 no total. Ciências da Natureza ocupa 91–135 e Matemática 136–180 nesses cadernos; essa faixa é uma regra do perfil desses documentos, não uma regra universal para qualquer PDF.

| Fonte | Arquivo | SHA-256 do original |
|---|---|---|
| Prova 2024 | `2024_PV_impresso_D2_CD5.pdf` | `ec4e704ab4017762ffb1eba84c55285a429d3d02ed0e58258c1171315cb34937` |
| Gabarito 2024 | `2024_GB_impresso_D2_CD5.pdf` | `342edd1d18c0266812b9e379c7b9b2ebfcdd739857445bd03cf3c55951861297` |
| Prova 2025 | `2025_PV_impresso_D2_CD5.pdf` | `0a59697676989b55e6f3e40636fad164c1c26868ddba37d04e4fffc101168298` |
| Gabarito 2025 | `2025_GB_impresso_D2_CD5.pdf` | `4feea3658a94e20fa226028824b22538cb1b7e405a6a6e547d6a7131e5c97c22` |

Execuções v5 de referência:

- 2024: `20261101T201410Z-70ac530d-v5`.
- 2025: `20261101T201422Z-f0fea3ad-v5`.

Essas execuções identificaram 13 questões críticas em 2024 e 10 em 2025. Há 85 letras atribuídas em 2024 e 86 em 2025: as demais incluem anulação e falha de extração. **Não interprete todo gabarito vazio como anulação.** As 171 letras atribuídas foram conferidas nas verificações anteriores; a falta de letras também precisa ser avaliada.

Na conferência humana parcial recebida em 05/11, houve quatro aprovações, 16 reprovações e três dúvidas; 157 não foram examinadas. Essa amostra foi dirigida a defeitos e não estima a qualidade geral das 180 questões. O responsável decidiu não exigir nova leitura humana integral das 180 para o piloto. Sua avaliação deve combinar validações automáticas do lote inteiro com uma referência menor e dirigida.

Foi discutido excluir do piloto os defeitos/dúvidas/alertas pendentes. Essa filtragem não foi implementada neste briefing e não deve remover os casos do conjunto de regressão do extrator: justamente eles mostram o que precisa melhorar.

## 4. Problemas que você precisa atacar

O problema não é somente “PDF para texto”. O desafio é preservar a estrutura e o significado da representação.

### 4.1 Casos reprovados pela conferência humana

| Ano/questão | Defeito registrado | Comportamento esperado |
|---|---|---|
| 2024 Q94 | Tabela de pH perde vírgulas/estrutura; setas de equilíbrio ficam ausentes no texto | Preservar relações da tabela e decimais; representar ou vincular corretamente as setas |
| 2024 Q139 | Frações/fatoriais ilegíveis, alternativa C vazia e fim do enunciado absorvido por A | Delimitar enunciado e A–E; recuperar expressões sem completá-las por suposição |
| 2024 Q141 | Alternativas com frações fragmentadas | Manter igualdade, numerador, denominador e associação a A–E |
| 2024 Q142 | Números mistos viram expoentes/linhas sem estrutura | Diferenciar número misto, fração e potência |
| 2024 Q149 | Somente A reconhecida; B–E fundidas; gabarito vazio apesar de letra E oficial | Cinco alternativas separadas e associação válida do gabarito |
| 2024 Q150 | Fórmula de magnitude/energia quebrada | Preservar subscritos, diferença, fator 2/3 e argumento do logaritmo |
| 2024 Q151 | C–E incorporadas em B; frações com π fragmentadas; gabarito D não associado | Separar A–E, reconstruir frações e preservar π |
| 2024 Q158 | Unidades fracionárias quebradas; B–E incorporadas em A; gabarito C ausente | Preservar unidades compostas, expoentes e fronteiras das alternativas |
| 2024 Q179 | Lista de alternativas vazia; A–E dentro do enunciado; gabarito C ausente | Reconstruir questão/alternativas sem confundir expoentes e frações |
| 2025 Q115 | Fórmula logarítmica fragmentada | Recuperar a fórmula; manter anulação do gabarito como condição independente |
| 2025 Q123 | Seta de equilíbrio `⇌`, desenhada como gráfico, ausente no texto | Preservar direção/tipo de seta na equação; não substituir equilíbrio por reação unidirecional |
| 2025 Q129 | Gráficos deslocados: A do PDF no enunciado, A–D ligados a B–E e E vazia | Relacionar cada gráfico à letra correta; não alterar o gabarito para compensar o deslocamento |
| 2025 Q159 | Equações nas alternativas ilegíveis, com fragmentos no enunciado | Preservar a estrutura e as diferenças entre expressões de A–E |
| 2025 Q164 | C–E dentro de B; frações T/F e F/T perdidas; gabarito C não associado | Cinco alternativas distintas, inclusive inversão de numerador/denominador |
| 2025 Q170 | Perda de expoente torna alternativas diferentes textualmente iguais | Preservar `m²/cd` versus `m/cd`, frações e símbolos |
| 2025 Q176 | C–E dentro de B; potências e frações quebradas | Preservar alternativas, potência decimal, sinais e denominadores |

Use os PDFs como fonte para construir os valores esperados. As descrições acima localizam os defeitos, mas não são transcrições completas aprovadas de cada questão.

### 4.2 Outros casos obrigatórios de referência

- Críticas ainda sem veredito humano: **2024 Q140/Q147/Q148; 2025 Q145/Q154/Q169**. Inspecione antes de atribuir causa exata; não invente o diagnóstico apenas pela semelhança com outras questões.
- **2024 Q104:** aprovada pela pessoa com nota sobre símbolo vetorial quebrado em linhas. A figura está preservada, mas o texto mantém `fragmented_formula`. Não use a aprovação como prova de que a normalização vetorial foi resolvida.
- **2024 Q102; 2025 Q121/Q178:** ficaram em dúvida. Os gabaritos oficiais examinados indicam anulação. Diferencie anulado, sem gabarito fornecido, leitura ambígua e letra sem alternativa correspondente. Mantenha a dúvida histórica até a decisão humana/curadoria correspondente.
- Controles: **2024 Q91 e Q106**, aprovadas com figuras, e **Q130**, aprovada de texto simples. O candidato não deve melhorar fórmulas destruindo os casos simples ou o vínculo das figuras.
- Outras figuras/gráficos/tabelas serão selecionados do lote antes do ajuste final, para não testar somente os defeitos usados no desenvolvimento.

## 5. Requisitos funcionais

### 5.1 Entrada e reconhecimento do documento

- Receber caminho de arquivo local de prova e, opcionalmente, de gabarito. Validar conteúdo/assinatura, limites e legibilidade.
- Identificar ou exigir metadados suficientes para ano, dia, caderno/cor e edição/aplicação. Não misturar gabaritos de cadernos diferentes.
- Aceitar PDF com texto nativo e detectar páginas/regiões que exigem OCR. No primeiro marco, um formato ainda não atendido pode ser recusado com causa explícita; não retornar sucesso com documento vazio.
- Preservar os bytes originais e seu hash. Renomear o mesmo arquivo não deve produzir outra identidade de fonte.

### 5.2 Layout e segmentação

- Reconstruir ordem de leitura em uma ou duas colunas, com regiões que atravessam a largura da página.
- Manter questão que continua na página seguinte e não incorporar conteúdo da questão vizinha.
- Detectar títulos/numeração e delimitar enunciado, textos de apoio, alternativas, legendas e fontes.
- Usar posição/estrutura junto dos marcadores; uma regex de letras isoladas é insuficiente.
- Remover mobiliário somente com evidência. Não apagar sequências científicas que parecem repetição, como cadeias químicas, sequências biológicas e números de tabelas.
- Toda região relevante deve aparecer no resultado ou em um registro de omissão/limite. Nunca descartar silenciosamente texto curto ou trecho difícil.

### 5.3 Texto, matemática e ciências

- Preservar conteúdo literal e ordem, sem resumir ou reescrever em linguagem “mais clara”.
- Preservar sinais, separador decimal, unidades, potência, base, subscrito, fração, raiz, fatorial, logaritmo e símbolos gregos.
- Química: distinguir índices e cargas, coeficientes, estados físicos, direção/tipo de seta e condições da reação.
- Física: manter vetor, módulo, sinal e unidade. Biologia: preservar sequências, rótulos, escalas e legendas sem normalização destrutiva.
- Escolher uma representação textual consistente para matemática, por exemplo LaTeX, documentando convenções. Não fornecer LaTeX inválido como se fosse extração fiel.
- Um recorte de página permite consultar o original, mas não corrige por si só uma fórmula quebrada no JSON.

### 5.4 Alternativas e gabarito

- Produzir A–E separadas, incluindo alternativas somente em imagem e grades com mais de uma coluna.
- Preservar ordem e diferenças entre alternativas; não “corrigir” distratores para parecerem verdadeiros.
- Vincular a letra oficial somente quando número, caderno e alternativa estiverem compatíveis.
- Registrar por que uma resposta está ausente. Conflito entre fontes, gabarito não fornecido, questão anulada e alternativa não extraída são condições diferentes.
- Nunca obter o gabarito resolvendo a questão por IA e apresentá-lo como oficial.

### 5.5 Figuras e tabelas

- Preservar imagens rasterizadas e conteúdo desenhado com vetores no PDF, com resolução/recorte suficientes para leitura.
- Associar recurso à questão e, quando aplicável, à alternativa específica. Testar identidade pela imagem, não apenas pelo número de recursos.
- Manter página, caixa de localização e hash do recurso em um manifesto rastreável.
- Representar tabelas com células, linhas, colunas, cabeçalhos e unidades quando recuperáveis. Guardar o recorte original para comparação.
- Para texto dentro de figuras, separar transcrição explícita de interpretação. Não inferir pontos de gráfico que não são legíveis nem descrever uma tendência como se fosse dado numérico impresso.
- Identificar recursos ainda sem transcrição textual. Figura visualmente íntegra não equivale a conteúdo inteiramente disponível ao RAG textual.

## 6. Estratégia técnica proposta

Comece com uma linha de base executável e só então compare uma nova abordagem. A recomendação é um pipeline por etapas com interfaces substituíveis:

1. **Admissão:** validar entrada, registrar fonte e reservar execução.
2. **Leitura/layout:** extrair blocos com posição, recursos e ordem de leitura.
3. **Segmentação:** obter regiões de questão e alternativas.
4. **Recuperação de regiões difíceis:** aplicar OCR matemático/visão ou outro parser nos trechos em que a leitura nativa não é suficiente.
5. **Reconciliação:** ligar a transcrição à região original e detectar conflito com a extração nativa.
6. **Validação:** verificar estrutura, símbolos/recursos relevantes e gabarito.
7. **Saída e relatório:** registrar dados, métodos, pendências e comparação com a execução anterior.

Essa é uma proposta, não a exigência de um parser específico. Você pode propor evolução incremental ou substituição do núcleo. A escolha precisa ser defendida com os mesmos PDFs, orçamento, defeitos e controles. Não é necessário criar agentes autônomos ou adicionar LangGraph ao extrator determinístico apenas porque a engine usa LangGraph.

Se houver chamadas de IA integradas ao projeto, aproveitar a fronteira de modelos existente quando adequada e preservar configuração, tratamento de falhas e consumo. Modelo, fornecedor de OCR, custo e limites de chamadas precisam ser definidos antes do ensaio pago. Credenciais ficam no ambiente; não no código, JSON, prompt de entrega ou log.

### OCR/visão e confiança

- OCR/visão é outra transformação, com fornecedor/modelo/versão/configuração registrados.
- Confiança do modelo não é medida de fidelidade ao PDF. Concordância entre duas leituras também não é prova suficiente.
- A transcrição não pode preencher um símbolo ou número só porque “faz sentido” na solução.
- Se duas leituras discordarem, guarde o conflito e a região; não escolha silenciosamente uma versão.
- Cada chamada precisa de limite de tempo, tentativas e consumo. Resposta perdida pode ter custo incerto; isso precisa aparecer no relatório.
- Não enviar PDFs/regiões a serviço externo sem o uso e os recursos correspondentes autorizados.

## 7. Saída e contrato de integração

### 7.1 Estrutura de arquivos existente a preservar ou adaptar

```text
dados/
  quarentena/<sha256>.pdf
  saida/
    sources/<source_id>/
      manifest.json
      current.json
      runs/<run_id>/
        questions/<question_id>.json
        assets/<hash>.<extensao>
        report.json
        relatorio.md
        conferencia.csv
    reviews/<question_id>.json
```

Datas e caminhos relativos não devem ser a única identidade da fonte. Os nomes de arquivos recebidos não podem virar caminhos internos irrestritos.

### 7.2 Registro de extração atual

O arquivo autoritativo de construção desse registro é `src/higgs/ingestion/records.py`. Ele é um **registro intermediário de extração**, não o `QuestionCandidate` de geração do contrato 1.1.0. Não force questões oficiais a incluir resolução, distratores ou campos gerados inexistentes só para caber no contrato da engine.

| Campo atual | Significado e cuidado |
|---|---|
| `record_version` | Versão do formato do registro, atualmente `"1"` |
| `question_id` | Atualmente `q-<12 primeiros caracteres do hash da fonte>-<número com 3 dígitos>`; preservar compatibilidade ou fornecer migração |
| `number` | Número oficial no caderno, não ordem arbitrária de um array |
| `status` | `extracted` ou `needs_review`; `extracted` não significa revisado por pessoa |
| `content_sha256` | Hash do conteúdo que a pessoa revisa, calculado pela rotina existente |
| `stem` | Enunciado preservado, com referências a recursos na posição pertinente |
| `choices` | Lista de `{letter, text, asset_ids}`; A–E precisam corresponder ao PDF |
| `tables` | Atualmente lista de textos; uma representação mais rica exige compatibilidade/versionamento |
| `answer` | Atualmente `{letter, origin, origin_label}`; `letter` pode ser nulo |
| `location` | `{page_start, page_end}`; páginas contam desde 1 no PDF |
| `source` | Referência à origem, versão e hash do original |
| `assets` | Referências a recursos: hash, tipo, fonte e página |
| `snapshots` | Recortes para conferência, separados dos recursos originais da questão |
| `issues` | Achados com `code`, `severity`, `message`, página/questão quando aplicáveis |
| `annotations` | Anotações com origem explícita; extração automática não cria `reviewed` |
| `provenance` | Versão da transformação, extrator/versão, execução e rótulo da fonte |
| `reprocessing` | Informação anexada pelo armazenamento sobre mudança e revisões obsoletas |

**Detalhes de compatibilidade importantes:**

- `source_id` do diretório/manifesto é o SHA-256 completo do PDF. A referência `source.source_id` no JSON usa hoje um identificador com prefixo `src-` e hash abreviado. Não confunda esses identificadores ao importar conferência.
- `asset_id` do contrato usa prefixo/abreviação; os `asset_ids` das alternativas usam atualmente o hash completo. Referências textuais como `[[figura:...]]` podem usar abreviação. Preserve a resolução de todos eles; não use a coincidência de strings como suposição universal.
- Hoje o registro final não expõe todos os `bbox` das estruturas intermediárias. Para aumentar rastreabilidade, proponha um manifesto de regiões ou uma extensão versionada; não afirme que todo campo atual já tem coordenadas próprias.
- `answer.origin` identifica o hash do gabarito, não apenas o nome do arquivo.
- O hash atual cobre enunciado, alternativas/recursos, tabelas e resposta/origem. Uma transcrição nova que mudar o conteúdo revisável precisa participar da identidade da versão, com a regra documentada.

Não altere o algoritmo de hash ou renomeie IDs por conveniência sem estudar os históricos de revisão e fornecer compatibilidade. Se você precisar de formato próprio internamente, entregue um adaptador testado para a fronteira combinada.

### 7.3 Melhorias de contrato a propor

Há lacunas que não devem ser resolvidas com valores sobrecarregados:

- Estado de gabarito: encontrado, anulado, não fornecido, ambíguo ou incompatível.
- Representação original e normalizada de matemática, com ligação à região do PDF.
- Transcrição de figura e seu método/versão, distinta de descrição inferida.
- Prontidão visual e textual separadas; não usar aprovação genérica para apagar incerteza.

Esses estados/nomes são propostas conceituais, **não campos já publicados**. Documente um schema e exemplos antes de mudar consumidores. Combinar com quem mantém curadoria/persistência; a implementação do extrator não pode definir sozinha o contrato final do dataset.

## 8. Validação, falha e reprocessamento

### Validações obrigatórias

- Intervalo esperado de questões, sem números ausentes/duplicados; ausências devem ser explicadas.
- Enunciado não vazio; A–E presentes quando esse é o formato da fonte.
- Referências de imagens existentes, com hash correto e associação verificável.
- Letras de gabarito coerentes com alternativas e identidade do caderno.
- Sinais de glifos quebrados, caracteres de objeto/substituição, fórmulas/frações fragmentadas e alternativas fundidas.
- Colunas/tabelas e decimal coerentes nos casos de referência; quantidade de caracteres sozinha não é oráculo.
- Tempo excedido, recurso omitido, falha de OCR e limite de quota viram erro/pendência explícitos.

Não reduza alertas simplesmente tornando o detector menos sensível. A redução deve vir de representação melhor ou de classificação justificada por evidência. Um resultado parcial pode existir, mas o resumo precisa informar o que não foi extraído e o que não está elegível.

### Reprocessamento

Nova execução não sobrescreve arquivos antigos. Atualização de `current.json` deve ser atômica. Execuções concorrentes não podem colidir.

Uma revisão humana vale para a versão/hash que foi examinada. Alteração de texto, alternativa, recurso, gabarito ou transcrição revisável não pode herdar aprovação de outra versão. O sistema atual registra `review_stale`; preserve a propriedade mesmo que mude a organização interna.

Nunca crie `origin="reviewed"` a partir de resposta de OCR, classificação ou parecer de agente. Registre método automático e deixe a decisão humana em seu fluxo próprio. Esta entrega não autoriza substituir a política de curadoria humana por aprovação automática.

## 9. Segurança e operação da ferramenta

Embora os PDFs iniciais sejam oficiais, o parser lê conteúdo externo e usa bibliotecas nativas. Preserve isolamento real do processo:

- Processo de parser/OCR local sem credenciais, com filesystem restrito e rede negada quando não necessária.
- Limites configuráveis de bytes, páginas, imagens, pixels agregados, tempo, CPU, memória e volume de saída, conforme suporte do sistema.
- Diretórios temporários exclusivos; rejeição de traversal e referências a arquivos fora da raiz permitida.
- Falha fechada quando o isolamento exigido estiver indisponível. Não desabilitar sandbox para obter um teste verde.
- macOS e Linux: declarar o backend testado. Suporte a Windows nativo ou WSL deve ser explicitamente implementado e verificado antes de anunciado.
- Bibliotecas de renderização não devem buscar links encontrados no PDF automaticamente. Conteúdo do documento não é instrução para executar código/ferramentas.
- Preview com escape de conteúdo; CSV com proteção contra execução de fórmulas, preservando o JSON original.

O componente atual já teve uma falha real em CI Linux por montagens de symlinks do interpretador no `bwrap`. Não remova os testes de efeito negado ou a sonda funcional de backend. Veja o histórico em `docs/INGESTAO.md` e nos testes.

PyMuPDF é hoje dependência opcional da ferramenta interna (`ingestao`), separada do código implantado do produto. Qualquer substituição deve registrar dependências, versões, licença e restrições de uso/distribuição. Não presumir que todo componente instalado é adequado à distribuição pretendida; a escolha deve ser combinada com o responsável.

## 10. Plano de avaliação sem conferir manualmente as 180 novamente

O custo humano é uma restrição explícita. A proposta é:

1. **Rodar as 180 automaticamente:** checagem de estrutura/recursos/gabarito, diferenças por campo, alertas, tempo e consumo. Essa checagem é cobertura operacional, não certificação da fidelidade completa.
2. **Montar uma referência dirigida:** priorizar os 16 defeitos registrados, os seis críticos ainda pendentes e Q104, mais as anulações e controles. Aproveitar a conferência recebida e o PDF; completar somente os campos necessários ao teste que ainda não têm referência confiável.
3. **Separar desenvolvimento e aceitação:** reservar um pequeno lote adicional de casos/recortes antes de ajustar a solução. Evitar medir apenas as questões cujas respostas já orientaram as heurísticas. Esse teste do extrator é distinto do split exemplos/avaliação da engine.
4. **Conferir por pessoa apenas pontos de risco/diferenças relevantes**, conforme disponibilidade acordada. Sem anotação confiável ou leitura conclusiva, o resultado permanece incerto, em vez de contabilizar um acerto inventado.
5. **Comparar baseline e candidato no mesmo conjunto:** publicar quais defeitos foram corrigidos, mantidos ou introduzidos. Não extrapolar uma amostra dirigida para taxa de acerto global.

### Métricas mínimas do relatório

| Dimensão | O que medir |
|---|---|
| Cobertura | Questões encontradas/esperadas, ausências, repetições, páginas sem conteúdo |
| Estrutura | Questões com enunciado e A–E separados corretamente na referência |
| Fidelidade crítica | Casos com número/sinal/expoente/fração/unidade/seta alterados |
| Recursos | Associação questão/alternativa–figura, integridade/legibilidade e omissões |
| Gabarito | Letras associadas corretamente; anulações e causas de ausência explícitas |
| Detecção | Defeitos detectados, defeitos silenciosos e falsos alarmes no conjunto anotado |
| Eficiência | Tempo total/por etapa, volume de OCR/chamadas e custo conhecido/incerto |
| Esforço humano | Quantos casos/trechos exigem intervenção e tempo observado quando medido |

Sem referência de verdade, reporte “não medido”. Um JSON válido, cinco alternativas e nenhuma exceção não comprovam extração fiel.

## 11. Marcos de entrega propostos

### Marco A — reproduzir e fechar o contrato

Entregar instruções de instalação, execução da baseline, inventário de problemas, amostra de saída e proposta de arquitetura/formato compatível. Explicar o que manter/substituir e qual evidência decidirá. Definir recursos/modelos/orçamento antes de chamadas pagas. O responsável confirma o recorte e o contrato antes de consumidores novos.

### Marco B — recuperação dos casos críticos

Implementar o caminho completo de um grupo real de falhas, incluindo recursos e modo de erro; depois ampliar aos grupos priorizados. Entregar exemplos antes/depois, teste independente do caso e resultado ligado ao PDF. Não criar uma tabela fixa de respostas por ano/número: as regras devem operar sobre o documento e generalizar.

### Marco C — integração e demonstração reproduzível

Executar os dois cadernos, preservar o histórico e entregar relatório comparativo, registros de regiões/transcrições, pendências e compatibilidade com conferência/curadoria. Acrescentar testes pertinentes e instruções para outra pessoa rodar a partir de um checkout limpo.

Esses marcos não exigem três PRs nem autorizam reescrever áreas fora da tarefa; servem para tornar a entrega revisável durante o desenvolvimento.

## 12. Critérios de aceite propostos para esta entrega

- [ ] Ambiente reproduzível, versões fixadas e execução sem caminhos pessoais.
- [ ] Dois cadernos processados com 90 identidades de questão cada, ou falha/incompletude explicitamente reportada; nenhum conteúdo perdido em silêncio.
- [ ] Original, recursos e versões preservados; todas as referências resolvem.
- [ ] Contrato compatível com os consumidores existentes ou adaptação/migração documentada e testada.
- [ ] Cada caso crítico priorizado tem um resultado individual: corrigido com evidência ou ainda pendente, sem declaração falsa de recuperação.
- [ ] A primeira entrega de melhoria demonstra redução de defeitos críticos na referência, não apenas uma nova interface ou mais alertas.
- [ ] Casos preservados do baseline não apresentam regressão crítica conhecida; diferenças novas foram examinadas e reportadas.
- [ ] Gabarito vazio não é tratado automaticamente como anulado, e letras não são inventadas.
- [ ] Figura, transcrição textual e snapshot são distinguidos; conteúdo visual faltante não é ocultado por resumo gerado.
- [ ] Reprocessamento e hash invalidam revisão antiga quando o conteúdo revisável muda.
- [ ] Erro, timeout, consumo/quota e conflito entre leituras ficam visíveis; dados incompletos não viram sucesso limpo.
- [ ] Testes demonstram isolamento e falha fechada no ambiente declarado, inclusive o caminho real que usa o parser/OCR.
- [ ] Relatório informa conjunto, denominadores, resultados, custo/tempo e limites; não alega 100% de fidelidade sem evidência.
- [ ] Nenhuma aprovação humana, release de dataset ou split de avaliação foi criado por inferência automática.

Não há meta numérica nova de precisão/custo aprovada neste briefing. Depois da baseline, propor metas de melhoria com conjunto e denominador explícitos, e combiná-las antes da avaliação final. O desenvolvedor não deve baixar metas depois de observar o teste para encerrar a entrega.

Se a entrega for integrada ao repositório atual, vale o critério de revisão existente: nota mínima 95/100, ausência de bloqueios e CI verde no commit revisado. Essa nota mede o aceite técnico do código; não equivale à taxa de fidelidade dos PDFs.

## 13. O que entregar ao responsável

1. Código e testes com instrução de execução a partir de clone limpo.
2. Dependências fixadas, configuração de exemplo sem segredos e requisitos de sistema.
3. Documento do formato de saída, compatibilidade e identidade/versionamento.
4. Resultados dos PDFs de referência: JSONs, recursos, relatórios e localização das execuções.
5. Relatório baseline × candidato por caso/grupo e mudanças de conteúdo/hash, com falhas remanescentes.
6. Evidência dos testes executados, incluindo os que falharam ou não puderam rodar.
7. Lista de decisões ainda necessárias, custos observados e limitações conhecidas.
8. Passagem curta com commit, comandos, como reproduzir um caso recuperado e um caso ainda incerto.

Trabalhe em branch/workspace próprio, sem alterar `main` diretamente ou escrever sobre arquivos que outro desenvolvedor está modificando. Se for um repositório novo, combine primeiro a fonte oficial, o contrato e como a entrega será integrada; não mantenha duas implementações do produto divergindo sem responsável. Não publique provas/dados nem envie PRs/mensagens em nome do responsável sem autorização correspondente.

## 14. Materiais de apoio e responsabilidades pendentes

O responsável deve disponibilizar, sem credenciais pessoais:

- Os quatro PDFs identificados na seção 3.
- As duas execuções v5 completas: JSONs, recursos, manifestos e CSVs.
- A devolução humana parcial e seu relatório de análise.
- Acesso ao código/testes ou snapshot autorizado.
- Disponibilidade para adjudicar um conjunto reduzido de campos/casos, em vez de exigir revisão integral das 180.
- Modelo/fornecedor e teto de custo, caso a solução use OCR/visão externo.

Este Markdown é autossuficiente para entender a missão, mas não incorpora os PDFs, o acervo ou o código. Os caminhos abaixo são referências relativas ao repositório, disponíveis quando você receber o checkout:

- [Visão do produto](VISAO_GERAL_DO_PROJETO.md) e [plano do projeto](PLANO_DO_PROJETO.md).
- [Preparo do dataset fora do produto](PREPARO_DO_DATASET.md).
- [Extrator atual e comandos](INGESTAO.md). Há seções históricas com versões/limites antigos; conferir os adendos e o código vigente.
- [Modelos intermediários](../src/higgs/ingestion/models.py), [registro atual](../src/higgs/ingestion/records.py) e [pipeline](../src/higgs/ingestion/pipeline.py).
- [Testes de ingestão](../tests/ingestion/) e [regras de trabalho](../sprints/README.md).
- [Conferência histórica por IA](../auditorias/conferencia_ia_extracao_enem_2026-11-01.md) e [análise da devolução humana](../auditorias/auditoria_devolucao_conferencia_humana_2026-11-05.md).
- [Critério de aprovação de código](CRITERIO_DE_APROVACAO_DE_CODIGO.md).

Skills locais de engenharia são auxiliares opcionais de desenvolvimento; não são pré-requisito para um desenvolvedor humano compreender ou executar o projeto, nem autorização para produzir revisão humana automaticamente.

**Primeira ação esperada:** reproduzir a baseline nos dois PDFs, analisar os casos de falha, apresentar uma proposta de evolução compatível e uma primeira entrega que recupere conteúdo real com evidência. O resultado desejado é um extrator melhor e menos esforço manual, com limites honestos sobre o que ainda não consegue ler.

# Contrato integrado da Arena Aurora — v1

**Status:** contrato de integração para a primeira fatia determinística; não declara implementada uma evolução urbana anual.

Este documento conecta estado, propostas/orçamento, indicadores e relógio de rodada. As três fontes originais foram copiadas sem edição para esta pasta. Elas descrevem, em alguns pontos, recomendações ou domínios futuros; este contrato distingue essas recomendações do que o YAML e o código realmente autorizam.

## 1. Precedência e resolução rastreável

Em conflito, aplicar a seguinte ordem, sem apagar a divergência da fonte:

1. Decisões solicitadas explicitamente para esta integração e valores do perfil versionado `configs/cities/aurora-base-v1.yaml`.
2. Comportamento já implementado e coberto por código/testes, como evidência de capacidade, não de validade empírica.
3. Contratos específicos de estado, rodada/ações e indicadores, respeitando os rótulos “implementado”, “recomendado”, “proposto” e “em aberto” de cada fonte.
4. Arquitetura específica de Aurora antes de texto conceitual geral antigo quando houver divergência. A própria especificação de rodadas registra esse critério para duração anual e horizonte.

| Tema divergente ou incompleto | Resolução integrada | Evidência/limite |
|---|---|---|
| Conceito antigo deixa duração da rodada em aberto | Uma rodada representa um ano sintético; horizonte padrão 10. | YAML `arena`; estado §3.4; rodadas §2. |
| 100 CS poderiam ser confundidos com verba de ação | Manter a alocação 60/10/30. Para esta fatia, registrar o envelope e zero gasto; só os 30 discricionários são o limite recomendado para novas ações. Não criar saldo, receita, dívida nem cobrança de operação. | YAML `finance`; rodadas §3.4. O uso de reserva, expiração/rolagem e compromissos futuros permanece aberto. |
| O exemplo conceitual contém `budget_request` do agente | Não é autoridade nem entrada de custo. O custo seria calculado pelo servidor a partir de catálogo versionado; como o catálogo executável não existe, ações com efeito ficam indisponíveis. | Rodadas §§3.2, 3.4 e 5. |
| Ações e modelos anuais são descritos como roadmap, sem tarifas/dinâmicas implementadas | Não aplicar ações urbanas nem simular demografia, economia, habitação, serviços, finanças ou ambiente. | Estado §§1, 3.4 e 4; rodadas §§2–4; código atual. |
| `no_action` aparece como política de referência, mas não define evolução anual de domínios | Proposta vazia válida. O primeiro ciclo implementado confirma apenas o registro da Arena e preserva o hash/valores da cidade; marca `domain_transition=not_run` e não afirma que os domínios avançaram. | YAML `arena.reference_policies`; rodadas §3.2. A semântica científica de um ano sem modelos ainda precisa ser decidida antes de publicar resultado anual. |
| Catálogo enumera indicadores com fórmulas, mas parte dos insumos/modelos falta | Não sintetizar vetor de indicadores no ciclo sem ação. Métrica ausente é indisponível, nunca zero. Métricas SUMO existentes só se aplicam à janela de mobilidade e são sintéticas/simuladas; não anualizar. | Indicadores §§1–3, 9–10; estado §3.3. |
| Score/ranking | Avaliação é painel multidimensional/Pareto; não há score universal nem agregação de unidades distintas. | YAML `arena.default_scoring` e `universal_single_score`; catálogo §§1–2, 10. |

## 2. Interfaces comuns

### Estado e identidade

- A raiz é o snapshot canônico `aurora-base-v1`, gerado deterministicamente do YAML e identificado por `snapshot_id` e SHA-256 do payload canônico. Esse hash identifica o estado inicial, não uma rodada.
- Cada instância recebe cópia independente. A rodada recebe `experiment_id`, `instance_id`, `round_index`, snapshot inicial, hash do estado pai e, depois do primeiro commit, hash do registro de rodada pai.
- O estado candidato não altera nem reutiliza mutavelmente o snapshot de entrada. A fatia atual carrega os dados da cidade sem alterações e mantém separados `city_state_hash` e `round_record_hash`.
- Valores de Aurora permanecem sintéticos. As fontes IBGE são apenas os proxies explicitamente descritos no YAML; nada passa a ser `observed` por integração.

### Proposta, política e orçamento

- Uma proposta contém uma sequência tipada de ações. `no_action` é a sequência vazia e não tem custo nem efeito urbano.
- O envelope configurado é 100 CS/rodada: 60 operação fixa, 10 reserva e 30 discricionários. CS não é BRL. A fatia registra o envelope, 30 CS como limite discricionário nominal e zero comprometido/gasto; não mantém caixa nem saldo acumulado.
- `fixed_rule` permanece apenas referência configurada. Não há regra ou catálogo que autorize sua execução.
- Tarifas, custo recorrente, regras de compromisso, atrasos, alvos, conflitos e efeitos das famílias de ação precisam ser definidos/versionados antes de habilitar ações.

### Rodada, resultado e indicadores

- Relógio: `round_index = synthetic_year`, começando em 1; horizonte padrão 10.
- A ordem futura de uma rodada completa é candidato isolado → validações → modelos habilitados na frequência declarada → indicadores derivados com proveniência → registro/commit único.
- O único ciclo executável nesta fatia é um commit **de protocolo** para a política `no_action`. `domain_transition=not_run` explicita que o ano da cidade não foi modelado. Ele não produz resultado científico anual ou indicador final.
- Mobilidade usa `weekday_am_peak`/`weekday_off_peak` conforme selecionado, com semente e entradas versionadas. Saídas ficam como `simulated` (e cálculos derivados como `derived`), limitadas à janela e ao escoamento declarados; jamais multiplicadas para representar ano.
- Finanças públicas, habitação, serviços, ambiente e equidade não são computáveis como resultados de rodada sem os insumos/modelos/fontes definidos em suas fichas. Ausência permanece nula/não calculável com motivo.

## 3. Invariantes do primeiro ciclo

Validar antes de confirmar o registro:

1. A configuração e o snapshot identificam a mesma cidade; o hash de entrada confere com o snapshot gerado para a configuração.
2. `round_index` é o próximo inteiro esperado; o hash do pai coincide com o estado comprometido atual; o hash do registro pai coincide com a cadeia da instância.
3. A proposta de referência `no_action` contém zero ações; custo e gasto discricionário são zero, não negativos e não excedem 30 CS. A alocação 60+10+30 fecha em 100 CS.
4. O estado candidato continua satisfazendo balanços já definidos: total/população urbana/entorno, residentes e empregos distritais, e a alocação configurada de créditos. Nenhum balanço novo é inferido.
5. `city_state_hash` e conteúdo do snapshot candidato permanecem iguais ao pai nesta política; o snapshot inicial e cópias irmãs não mudam.
6. A fatia não emite indicadores nem saída SUMO. Toda saída futura deve declarar unidade, período, proveniência, produtor/versão e entradas; janela de mobilidade não vira dado anual.
7. O registro é serializado canonicamente e encadeado por hash. Uma falha de validação ou pai obsoleto não substitui o estado/registro confirmado.

O commit atual é atômico em memória por substituição de um único agregado imutável de armazenamento. Isso prova a fronteira local e o controle compare-and-swap dentro do processo; não substitui persistência transacional durável para produção.

## 4. Registro reprodutível

Cada ciclo registrado guarda versão do contrato, experimento/instância, rodada/ano sintético, política e proposta vazia, snapshot e hash de entrada, hash do estado pai/candidato, hash do registro pai, envelope de orçamento e gasto zero, status de transição de domínio, proveniência sintética e hash do próprio registro. Repetição com os mesmos IDs, estado pai e conteúdo produz o mesmo hash; conteúdo alterado sob a mesma posição não é aceito como retry equivalente.

O ciclo não contém manifesto de agente, modelo anual, semente exógena ou indicadores, pois nenhum deles foi executado. Isso é incompletude explícita do escopo, não evidência reproduzível de evolução urbana.

## 5. Questões necessárias para uma rodada urbana completa

- Quais modelos de domínio avançam no primeiro release e com quais equações, unidades, relógios, parâmetros e tratamento de ausência?
- O que significa cientificamente um ano sem ação quando modelos anuais estiverem habilitados; quais efeitos exógenos existem e como são pareados?
- Quais ações ficam ativas, seus schemas, alvos, autoridade, tarifas pontuais/recorrentes, compromissos, custos, conflitos, atrasos e ordem de efeitos?
- A reserva pode ser usada? O orçamento não gasto expira ou acumula? Como compromissos recorrentes e falhas afetam o envelope sem introduzir receitas/dívida implícitas?
- Quais campos da observação são públicos e como são versionados? Quais regras de retry, persistência durável e tolerância de reprodução serão garantidas?
- Quais saídas de modelo/indicadores são exigidas para chamar uma rodada de resultado; que dados e validação independente sustentam cada alegação empírica?

## 6. Fontes preservadas

- [Estado da cidade v1](estado-cidade-v1.md)
- [Rodadas, ações e orçamento v1](rodadas-acoes-v1.md)
- [Catálogo de indicadores v1](catalogo-indicadores-v1.md)
- Configuração de referência: `configs/cities/aurora-base-v1.yaml`.

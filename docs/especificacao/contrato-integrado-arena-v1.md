# Contrato integrado da Arena Aurora — v1

**Status:** contrato legado da fatia somente de protocolo; a semântica-alvo e as decisões de evolução anual estão em [contrato-evolucao-urbana-v1.md](contrato-evolucao-urbana-v1.md). Este documento não declara implementada uma evolução urbana anual.

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
| 100 CS poderiam ser confundidos com verba de ação | O ciclo legado só registra envelope e gasto zero. Para o contrato-alvo, adotar teto discricionário de 30 CS, reserva de 10 inacessível e expirada, sem carry-over; compromissos recorrentes ocupam o teto do ano em que vencem até o fim do horizonte. | YAML `finance`; contrato-evolucao-urbana-v1.md §5. |
| O exemplo conceitual contém `budget_request` do agente | Não é autoridade nem entrada de custo. O custo seria calculado pelo servidor a partir de catálogo versionado; como o catálogo executável não existe, ações com efeito ficam indisponíveis. | Rodadas §§3.2, 3.4 e 5. |
| Ações e modelos anuais são descritos como roadmap, sem tarifas/dinâmicas implementadas | Não aplicar ações urbanas nem simular demografia, economia, habitação, serviços, finanças ou ambiente. | Estado §§1, 3.4 e 4; rodadas §§2–4; código atual. |
| O identificador legado `no_action` designava apenas protocolo vazio | Na fatia de protocolo, o comportamento executável é `protocol_noop`, preserva a cidade e marca `domain_transition=not_run`. No contrato-alvo, `no_action` é proposta vazia **com transições anuais de referência**. Não reutilizar o identificador legado sem versionar/migrar a semântica. | Código atual; contrato-evolucao-urbana-v1.md §§1, 3 e 9. |
| Catálogo enumera indicadores com fórmulas, mas parte dos insumos/modelos falta | Não sintetizar vetor de indicadores no ciclo sem ação. Métrica ausente é indisponível, nunca zero. Métricas SUMO existentes só se aplicam à janela de mobilidade e são sintéticas/simuladas; não anualizar. | Indicadores §§1–3, 9–10; estado §3.3. |
| Score/ranking | Avaliação é painel multidimensional/Pareto; não há score universal nem agregação de unidades distintas. | YAML `arena.default_scoring` e `universal_single_score`; catálogo §§1–2, 10. |

## 2. Interfaces comuns

### Estado e identidade

- A raiz é o snapshot canônico `aurora-base-v1`, gerado deterministicamente do YAML e identificado por `snapshot_id` e SHA-256 do payload canônico. Esse hash identifica o estado inicial, não uma rodada.
- Cada instância recebe cópia independente. A rodada recebe `experiment_id`, `instance_id`, `round_index`, snapshot inicial, hash do estado pai e, depois do primeiro commit, hash do registro de rodada pai.
- O estado candidato não altera nem reutiliza mutavelmente o snapshot de entrada. A fatia atual carrega os dados da cidade sem alterações e mantém separados `city_state_hash` e `round_record_hash`.
- Valores de Aurora permanecem sintéticos. As fontes IBGE são apenas os proxies explicitamente descritos no YAML; nada passa a ser `observed` por integração.

### Proposta, política e orçamento

- Uma proposta contém uma sequência tipada de ações. `no_action` é proposta vazia, sem custo de ação; o efeito anual de referência é definido pelo contrato-alvo. `protocol_noop` designa exclusivamente o ciclo legado sem transição.
- O envelope configurado é 100 CS/rodada: 60 operação fixa, 10 reserva e 30 discricionários. CS não é BRL. A fatia registra o envelope, 30 CS como limite discricionário nominal e zero comprometido/gasto; não mantém caixa nem saldo acumulado.
- `fixed_rule` permanece apenas referência configurada. Não há regra ou catálogo que autorize sua execução.
- Tarifas, custo recorrente, regras de compromisso, atrasos, alvos, conflitos e efeitos das famílias de ação precisam ser definidos/versionados antes de habilitar ações.

### Rodada, resultado e indicadores

- Relógio: `round_index = synthetic_year`, começando em 1; horizonte padrão 10.
- A ordem futura de uma rodada completa é candidato isolado → validações → modelos habilitados na frequência declarada → indicadores derivados com proveniência → registro/commit único.
- O único ciclo executável nesta fatia é um commit **de protocolo** para `protocol_noop`. `domain_transition=not_run` explicita que o ano da cidade não foi modelado. Ele não produz resultado científico anual ou indicador final.
- Mobilidade usa `weekday_am_peak`/`weekday_off_peak` conforme selecionado, com semente e entradas versionadas. Saídas ficam como `simulated` (e cálculos derivados como `derived`), limitadas à janela e ao escoamento declarados; jamais multiplicadas para representar ano.
- Finanças públicas, habitação, serviços, ambiente e equidade não são computáveis como resultados de rodada sem os insumos/modelos/fontes definidos em suas fichas. Ausência permanece nula/não calculável com motivo.

## 3. Invariantes do primeiro ciclo

Validar antes de confirmar o registro:

1. A configuração e o snapshot identificam a mesma cidade; o hash de entrada confere com o snapshot gerado para a configuração.
2. `round_index` é o próximo inteiro esperado; o hash do pai coincide com o estado comprometido atual; o hash do registro pai coincide com a cadeia da instância.
3. A proposta de referência `no_action` contém zero ações; custo e gasto discricionário são zero, não negativos e não excedem 30 CS. A alocação 60+10+30 fecha em 100 CS.
4. O estado candidato continua satisfazendo balanços já definidos: total/população urbana/entorno, residentes e empregos distritais, e a alocação configurada de créditos. Nenhum balanço novo é inferido.
5. Em `protocol_noop`, `city_state_hash` e conteúdo do snapshot candidato permanecem iguais ao pai; o snapshot inicial e cópias irmãs não mudam. `no_action` anual é coberta pelos critérios do contrato-alvo e não por este invariante de protocolo.
6. A fatia não emite indicadores nem saída SUMO. Toda saída futura deve declarar unidade, período, proveniência, produtor/versão e entradas; janela de mobilidade não vira dado anual.
7. O registro é serializado canonicamente e encadeado por hash. Uma falha de validação ou pai obsoleto não substitui o estado/registro confirmado.

O commit atual é atômico em memória por substituição de um único agregado imutável de armazenamento. Isso prova a fronteira local e o controle compare-and-swap dentro do processo; não substitui persistência transacional durável para produção.

## 4. Registro reprodutível

Cada ciclo registrado guarda versão do contrato, experimento/instância, rodada/ano sintético, política e proposta vazia, snapshot e hash de entrada, hash do estado pai/candidato, hash do registro pai, envelope de orçamento e gasto zero, status de transição de domínio, proveniência sintética e hash do próprio registro. Repetição com os mesmos IDs, estado pai e conteúdo produz o mesmo hash; conteúdo alterado sob a mesma posição não é aceito como retry equivalente.

O ciclo não contém manifesto de agente, modelo anual, semente exógena ou indicadores, pois nenhum deles foi executado. Isso é incompletude explícita do escopo, não evidência reproduzível de evolução urbana.

## 5. Requisitos ainda pendentes de implementação

- Implementar os modelos de domínio e parâmetros/unidades definidos em `contrato-evolucao-urbana-v1.md` e suas especificações acompanhantes.
- Implementar a migração versionada `no_action` legado → `protocol_noop`, mantendo `no_action` anual com transição no contrato-alvo.
- Integrar ações do catálogo-alvo; apenas anunciar uma ação quando schema, alvo, tarifa, validação e executor estiverem operacionais.
- Implementar a política de orçamento, compromissos recorrentes, atomicidade e atrasos congelada em `contrato-evolucao-urbana-v1.md`.
- Quais campos da observação são públicos e como são versionados? Quais regras de retry, persistência durável e tolerância de reprodução serão garantidas?
- Implementar as saídas disponíveis e `null`/motivos conforme catálogo; dados sintéticos não suprem validação independente.

## 6. Fontes preservadas

- [Estado da cidade v1](estado-cidade-v1.md)
- [Rodadas, ações e orçamento v1](rodadas-acoes-v1.md)
- [Catálogo de indicadores v1](catalogo-indicadores-v1.md)
- Configuração de referência: `configs/cities/aurora-base-v1.yaml`.

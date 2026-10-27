# Arquitetura do motor de evolução anual de Aurora — v1

**Status:** desenho de implementação alinhado ao contrato integrado; não implementado nem validado empiricamente.

Referência normativa: [`contrato-evolucao-urbana-v1.md`](../especificacao/contrato-evolucao-urbana-v1.md). Este documento define componentes, fronteiras e ordem de construção; não altera as regras científicas ou econômicas do contrato.

## 1. Objetivo e limites

Implementar dez rodadas anuais reproduzíveis para cinco instâncias independentes de `aurora-base-v1`. Cada agente decisor recebe observação equivalente e propõe ações para sua cidade. Regras determinísticas validam as propostas e calculam cada nova cidade. O agente nunca edita estado, calcula custo oficial ou chama diretamente o SUMO.

Aurora e os parâmetros v1 são sintéticos. A arquitetura não transforma resultados em previsão de uma cidade real, não calcula um ranking universal e não anualiza métricas SUMO de janelas.

## 2. Componentes e fronteiras

| Componente | Responsabilidade | Limite |
|---|---|---|
| `CityState` e `StateFactory` | Materializar estado inicial/evolutivo versionado e cópias isoladas; calcular hash canônico | Não mutar `CitySnapshot` nem compartilhar coleções mutáveis |
| `ExperimentManifest` | Congelar horizonte, perfil, parâmetros, versões, sementes, catálogo e regras | Defaults obrigatórios são materializados no início; ausência inválida falha |
| `ObservationBuilder` | Aplicar efeitos vencidos e produzir observação imutável para um ano | Agentes da mesma rodada recebem a mesma versão da observação |
| `AgentPolicy` | Converter observação em `ActionProposal`; inicialmente, política determinística de referência | Não acessa repositório, orçamento autoritativo, motor ou SUMO |
| `ActionArbiter` | Validar schema, autoridade, alvo, pré-condições, conflitos e custo | Calcula preço pelo catálogo; pacote inválido é rejeitado por inteiro |
| `AnnualTransitionEngine` | Aplicar ações aceitas e executar modelos anuais puros em ordem fixa | Modelos recebem candidato/eventos/parâmetros e retornam deltas; não fazem I/O |
| `MobilityAdapter` | Executar SUMO apenas quando solicitado, para janela configurada | Mantém resultado por janela; nunca anualiza nem atribui CO₂e sintético ao sinal |
| `IndicatorCalculator` | Produzir fichas tipadas de métricas disponíveis ou `null` com motivo | Preserva unidade, período, território, cobertura, método e proveniência |
| `InvariantValidator` | Conferir balanços, limites, tipos, proveniência e hashes antes do commit | Falha impede publicação de qualquer resultado parcial da cidade |
| `RoundRepository` | Carregar estado confirmado e salvar estado, efeitos, indicadores e recibo | Interface permite começar com adaptador em memória; não alegar durabilidade |
| `ArenaRunner` | Criar cinco cópias e coordenar participantes/rodadas | Não contém fórmulas de domínio nem lógica específica de provedor de IA |

O motor de domínio não importa FastAPI, SUMO, PostgreSQL ou SDK de modelo. A API valida e agenda trabalho; os pacotes de domínio calculam os resultados.

## 3. Contratos principais

```text
CityState
  experiment_id, instance_id, round_index, schema_version
  parent_city_state_hash, city_state_hash
  population, housing, employment, services, environment
  budget, pending_effects, active_signal_plans

Observation
  instance_id, round_index, city_state_hash
  state_view, available_actions, budget_view, indicator_values

ActionProposal
  proposal_id, agent_id, instance_id, round_index
  observed_city_state_hash, actions[]

RoundResult
  decision, action_receipts[], indicator_results[]
  parent_city_state_hash, city_state_hash, round_record_hash
  manifest_hash, provenance, diagnostics
```

Todos os contratos são versionados e estritos. Custos, fórmulas e parâmetros vêm do manifesto/catálogo, não do payload do agente. A proposta vazia é `no_action`; ausência ou erro do agente não deve ser reinterpretada silenciosamente como proposta vazia.

## 4. Sequência canônica anual

```text
estado confirmado
  → candidato isolado
  → aplicar efeitos com effective_round = r
  → congelar observação de r
  → coletar proposta de cada instância
  → validar proposta, conflitos e orçamento
  → aplicar ações aceitas ao candidato
  → população → habitação → empregos
  → serviços → área verde → CO₂e sintético
  → mobilidade SUMO opcional, por janela
  → validar invariantes, métricas e hashes
  → commit e publicação do resultado
```

Cada modelo anual roda exatamente uma vez. Os modelos anuais usam o candidato e os eventos efetivos do ano, na ordem normativa do contrato. Efeito semafórico aprovado ocorre após congelar a observação e só afeta a janela SUMO definida. Efeitos futuros recebem rodada efetiva explícita. Métrica sem insumo sai como `null` com motivo.

O commit valida `parent_city_state_hash` (compare-and-swap). Retry com a mesma identidade e conteúdo retorna o recibo anterior; identidade repetida com conteúdo diferente é conflito. Falha antes do commit preserva o estado confirmado. O hash de cidade depende apenas do payload canônico; o hash do registro da rodada avança a cada rodada.

## 5. Execução dos cinco agentes

1. Criar cinco `instance_id` com o mesmo snapshot raiz/hash e manifesto, cada um com estado e orçamento próprios.
2. Para o ano `r`, congelar uma observação independente por cidade, usando a mesma versão de política e o mesmo conjunto de informações comuns.
3. Executar políticas em paralelo ou serialmente; o resultado não pode depender da ordem de chegada.
4. Persistir proposta original e identidade/versionamento do agente antes da avaliação; para reprodução, reutilizar a proposta gravada, sem chamar novamente um modelo estocástico.
5. Validar cada proposta dentro de sua instância e registrar decisão, custos, efeitos e motivos.
6. Pausar o experimento diante de timeout/erro de participante até a política de falha ser congelada; não substituir erro por `no_action` nem comparar rodadas parciais como se fossem equivalentes.

Para a primeira versão, usar `AgentPolicy` determinística de referência. LLMs e treino PyTorch são adaptadores posteriores; não fazem parte do caminho científico do motor.

## 6. Estrutura inicial sugerida

Manter o domínio no pacote existente `packages/urban_arena`, sem fragmentar em serviços. Estrutura-alvo:

```text
urban_arena/
  state.py                 # estado evolutivo, factories e hashes
  manifest.py              # perfil e parâmetros congelados
  observations.py          # visão imutável para políticas
  actions.py               # propostas, catálogo, árbitro e recibos
  transitions/
    population.py
    housing.py
    employment.py
    services.py
    environment.py
  indicators.py            # fichas, nulls e proveniência
  round_engine.py          # pipeline determinístico e candidato
  repository.py            # interface e adaptador em memória
  arena.py                 # cinco instâncias e barreira de rodada
```

O adaptador de mobilidade continua em `packages/simulation`; `apps/api` orquestra jobs e expõe status/resultados. Persistência PostgreSQL/worker distribuído vem depois de estabilizar contratos e medir a necessidade.

## 7. Sequência de implementação

1. **Estado e manifesto:** adicionar schemas versionados para `CityState`, parâmetros materializados do perfil e hashes; preservar o snapshot inicial.
2. **Fatia vertical `no_action`:** uma rodada determinística sem ação, começando com população, habitação e empregos; validar balanços, hash e rollback antes de commit.
3. **Domínios restantes:** serviços, área verde, estimativa CO₂e, indicadores disponíveis e `null` com motivo.
4. **Ações e orçamento:** árbitro, pacote atômico e compromissos; habilitar apenas ações cuja integração esteja completa. Habitação/serviços permanecem desabilitados até os pré-requisitos contratuais.
5. **Arena de cinco instâncias:** política de referência determinística, observações/propostas gravadas, controle de falha/retry e isolamento de estados.
6. **SUMO:** conectar ajuste semafórico a uma janela definida, comparação controlada e exposição verificável; não alterar população ou emissão anual por inferência.
7. **Operação:** persistência durável, recuperação, concorrência entre workers e API de progresso quando os requisitos de execução justificarem.

## 8. Critérios de aceite da primeira fatia

- Mesmo snapshot, manifesto, estado pai e proposta vazia geram payload canônico e hash idênticos em duas execuções.
- `no_action` executa os modelos anuais obrigatórios; `protocol_noop` continua explicitamente sem transição de domínio.
- População, habitação e empregos reconciliam totais e balanços; nenhuma necessidade não atendida remove moradores implicitamente.
- Estado inicial permanece inalterado e candidato não vaza se validação falhar.
- Cada resultado identifica versão/perfil, origem sintética, método simulado/derivado, período e limitações.
- Campo sem insumo adequado é `null` com motivo, nunca zero fabricado.
- Cinco cópias começam com o mesmo hash e divergem apenas por transições/propostas próprias.

## 9. Decisões a congelar antes de comparar agentes

- Política de timeout, indisponibilidade e proposta inválida do agente; recomendação v1: marcar rodada como falha recuperável e pausar a avaliação, sem substituição implícita por `no_action`.
- Identidade/versionamento de cada agente: modelo/pesos, prompt ou política, parâmetros, seed e versão do adaptador.
- Política de retry e imutabilidade da proposta gravada.
- Se o experimento pausa globalmente quando uma instância falha e como retoma sem deixar cidades em anos diferentes.

Estas decisões afetam comparabilidade; devem ser versionadas no manifesto do experimento. Não são validação empírica das hipóteses de Aurora.

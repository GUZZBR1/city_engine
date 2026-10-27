# Urban Arena API

API local do MVP 0. A API usa `urban_arena.load_aurora_snapshot()` para carregar a
configuração e gerar o snapshot pelo núcleo Python. O `pyproject.toml` aponta para
`packages/urban_arena/` como dependência local editável.

```bash
python -m venv .venv
source .venv/bin/activate
uv pip install --python .venv/bin/python -e ./packages/urban_arena -e ./packages/simulation -e ./apps/api
uvicorn app.main:app --app-dir apps/api --reload
```

A API fica em `http://127.0.0.1:8000`; OpenAPI em `/docs` e `/openapi.json`.
Configure `API_CORS_ORIGIN` com a origem local do frontend (padrão
`http://localhost:5173`). Apenas `localhost` e `127.0.0.1` são aceitos.

Instale o SUMO no mesmo ambiente virtual que executa a API. O pacote oficial
`eclipse-sumo` fornece os comandos locais `sumo` e `netconvert`; ativar `.venv`
coloca ambos no `PATH` usado pelo worker da simulação:

```bash
source .venv/bin/activate
uv pip install --python .venv/bin/python eclipse-sumo
sumo --version
netconvert --version
```

O adaptador compila os controladores definidos no YAML de Aurora na rede
`.net.xml` e valida os links e fases antes de iniciar o SUMO. Veja
`packages/simulation/README.md` para os comandos, método de compilação e
limitações do benchmark sintético.

Rotas: `/api/v1/health`, `/api/v1/cities/aurora-base-v1`,
`/api/v1/cities/aurora-base-v1/map`, `POST /api/v1/simulations` e
`GET /api/v1/simulations/{simulation_id}`, `POST /api/v1/comparisons` e
`GET /api/v1/comparisons/{comparison_id}`, `POST /api/v1/arenas` e
`GET /api/v1/arenas/{arena_id}`. Jobs ficam em memória neste MVP
local e se perdem quando a API reinicia. Simulações e comparações rodam em
background após a resposta HTTP; arenas executam em `BackgroundTasks` também.
Essa descrição se refere a essas três rotas e não ao protocolo
`/api/v1/mobility-experiments`, que tem persistência e cancelamento descritos
abaixo.
O POST aceita `drain_limit_seconds` (inteiro entre 0 e 604800; padrão 3600),
que limita o tempo adicional para veículos solicitados terminarem após a janela
de demanda. O job retorna solicitadas, concluídas e não concluídas sem recalcular
as métricas do motor.

`POST /api/v1/arenas` cria um job anual para Aurora sintética. `horizon_rounds`
aceita inteiros entre 1 e 10 (padrão 10); `GET /api/v1/arenas/{arena_id}`
retorna o status, o manifesto, as cinco instâncias e os resultados das rodadas
com detalhes completamente serializados. `committed_rounds` conta confirmações
do motor; `completed_rounds` conta rodadas publicadas em `rounds`. Se a
serialização falhar após a confirmação, o job fica `failed`, mantém os hashes e
índices das cinco instâncias confirmadas, deixa `current_state` nulo se o estado
completo não pôde ser convertido e não publica detalhes parciais. Quando `sumo`
e `netconvert` estão disponíveis no `PATH` do processo da API, cada execução
compara uma política-base sem ações com quatro políticas semafóricas
determinísticas de benchmark. A ação aceita executa comparação pareada na janela
`weekday_am_peak`, com mesmo snapshot, demanda, semente 42 e limites. A evidência
`action_execution_evidence` permanece escopada à janela SUMO e não altera nem é
anualizada nos indicadores urbanos. As heurísticas são estratégias fixas, não
agentes IA treinados. Sem os binários, a Arena usa cinco políticas de referência
sem ações. Nenhum modo produz ranking agregado. A falha é retornada como job `failed` com código e mensagem,
preservando detalhes apenas das rodadas serializadas integralmente.

Jobs de simulação, comparação e Arena continuam usando memória do processo e
`BackgroundTasks`; reiniciar a API perde esses jobs. O experimento pareado
multi-semente descrito abaixo usa SQLite local e retoma trabalhos `queued` ou
`partial` ao iniciar a API. A execução da Arena calcula modelos anuais de
referência e, quando os binários estão disponíveis, executa comparações SUMO
por janela para ações semafóricas aceitas. Essa saída não representa tráfego
observado, validação empírica ou resultado anual.

Uma comparação aceita os mesmos parâmetros da simulação e uma intervenção
declarativa. O exemplo de Aurora mantém o ciclo em 66 s e altera somente as
durações do controlador `node:02:04`, que é alcançado por rotas do pico da manhã:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/comparisons \
  -H 'Content-Type: application/json' \
  -d '{"city_id":"aurora-base-v1","window_id":"weekday_am_peak","seed":42,"drain_limit_seconds":3600,"intervention":{"node_id":"node:02:04","phases":[{"movement":"north_south","duration_seconds":40},{"movement":"all_red","duration_seconds":3},{"movement":"east_west","duration_seconds":20},{"movement":"all_red","duration_seconds":3}]}}'
```

A resposta inicial contém o `comparison_id`; consulte
`GET /api/v1/comparisons/{comparison_id}` até `succeeded` ou `failed`. O
resultado inclui identidades das duas execuções, parâmetros comuns, métricas
originais do motor e deltas intervenção menos base. Se qualquer execução falhar,
a comparação não publica métricas nem deltas parciais. As métricas permanecem
sintéticas e não representam validação empírica. Se nenhuma rota da janela usar
uma transição que atravessa o controlador alterado, `route_exposure` será
`not_exposed`. O estado `exposed` exige ao menos uma rota completa e válida com
transição pelo nó. Arquivo ausente, malformado ou incompleto retorna
`route_exposure: "unknown"`; esses estados também são explicados nos avisos por
cenário.
O mapa usa `LocalFeatureCollection` em coordenadas cartesianas locais métricas,
nunca GeoJSON RFC 7946.

## Experimentos pareados Aurora multi-semente v1

Esta API implementa o protocolo `aurora-paired-multiseed-v1`. As rotas são:

| Método e rota | Uso | Resposta |
|---|---|---|
| `POST /api/v1/mobility-experiments` | Validar e congelar manifesto, expandir a matriz e enfileirar | `202` com `ExperimentCreateResponse` |
| `GET /api/v1/mobility-experiments/{experiment_id}` | Consultar ou fazer polling do experimento completo | `200` com `ExperimentResponse` |
| `POST /api/v1/mobility-experiments/{experiment_id}/retry` | Retomar pares incompletos com erro recuperável | `202` com `ExperimentResponse` |
| `POST /api/v1/mobility-experiments/{experiment_id}/cancel` | Solicitar cancelamento | `200` com `ExperimentCancelResponse` |

O `GET` é o endpoint de polling: consulte-o novamente até o estado geral ser
`succeeded`, `partial`, `failed` ou `cancelled`. Ele retorna todas as linhas
planejadas, não apenas as concluídas. A API não pagina `pairs` nesta versão.

### POST de criação

O corpo é um `MultiSeedManifestRequest`. Campos principais:

- `experiment_id` é opcional; quando fornecido, use de 1 a 128 caracteres
  `[A-Za-z0-9._-]`, começando por letra ou número. Sem ele, a API gera um ID
  determinístico. Reenvio do mesmo conteúdo é idempotente; reutilizar o mesmo
  ID com outro conteúdo retorna `409`.
- `arena_manifest_id`, `arena_manifest_sha256`, `round_index` e `instance_id`
  referenciam o contexto anual sem alterá-lo. `proposal_id`, `action_id` e
  `action_sha256` são opcionais.
- `city_id` deve ser `aurora-base-v1`. `window_ids` é a seleção explícita e
  `seeds` contém inteiros não negativos sem duplicatas. `strategies` não inclui
  o baseline e contém `strategy_id`, `policy_version`, `policy_sha256` e
  `intervention` (`node_id` mais quatro fases com `movement` e
  `duration_seconds`).
- `baseline_id`, `baseline_version` e `baseline_sha256` identificam o braço
  sem intervenção. Os hashes de política são SHA-256 da serialização JCS do
  payload efetivo: estratégia
  `{"policy_id":strategy_id,"policy_version":policy_version,"intervention":intervention}`;
  baseline `{"policy_id":baseline_id,"policy_version":baseline_version,"intervention":null}`.
  O servidor valida esses hashes antes de criar o manifesto.
- `drain_limit_seconds`, `metrics`, `metric_tolerances`, `primary_metrics`,
  `method_version`, `confidence_level`, `selection_method` e `master_seed`
  congelam as condições e o relatório. Tolerância é `{"exact":true}` para
  comparação exata, ou `{"absolute":n,"relative":n}`. Se `metrics` incluir
  `mean_travel_time_seconds` ou `mean_speed_kmh`, também precisa incluir
  `trips_requested`, `trips_completed` e `trips_not_completed`.
- `budget` contém `max_sumo_runs`, `max_attempts_per_execution`,
  `max_reproducibility_checks`, `max_wall_clock_seconds_per_run`,
  `max_total_wall_clock_seconds` e `admit_incomplete`. A mesma quantidade de
  verificações deve constar em `reproducibility_checks`; por enquanto ambos
  devem ser `0` porque a execução de verificações técnicas ainda não está
  implementada. Limites que não comportem o plano são rejeitados com `400`,
  salvo quando `admit_incomplete` foi declarado.

Exemplo abreviado do corpo (substitua os hashes pelos valores corretos):

```json
{
  "arena_manifest_id": "arena-1",
  "arena_manifest_sha256": "<64 hex>",
  "round_index": 1,
  "instance_id": "instance-1",
  "city_id": "aurora-base-v1",
  "window_ids": ["weekday_am_peak"],
  "seeds": [11, 17],
  "strategies": [{
    "strategy_id": "signal-policy-1",
    "policy_version": "v1",
    "policy_sha256": "<JCS hash of the applied policy payload>",
    "intervention": {
      "node_id": "node:02:04",
      "phases": [
        {"movement": "north_south", "duration_seconds": 40},
        {"movement": "all_red", "duration_seconds": 3},
        {"movement": "east_west", "duration_seconds": 20},
        {"movement": "all_red", "duration_seconds": 3}
      ]
    }
  }],
  "baseline_id": "baseline-no-action",
  "baseline_version": "v1",
  "baseline_sha256": "<JCS hash of baseline payload>",
  "drain_limit_seconds": 3600,
  "metrics": ["trips_requested", "trips_completed", "trips_not_completed", "mean_travel_time_seconds"],
  "metric_tolerances": {
    "trips_requested": {"exact": true},
    "trips_completed": {"exact": true},
    "trips_not_completed": {"exact": true},
    "mean_travel_time_seconds": {"absolute": 0.1, "relative": 0.01}
  },
  "primary_metrics": ["mean_travel_time_seconds"],
  "budget": {
    "max_sumo_runs": 8,
    "max_attempts_per_execution": 2,
    "max_reproducibility_checks": 0,
    "max_wall_clock_seconds_per_run": 120,
    "max_total_wall_clock_seconds": 960,
    "admit_incomplete": false
  },
  "reproducibility_checks": 0
}
```

`planned_pairs` é `estratégias × janelas selecionadas × seeds`; cada par tem
dois braços. Tentativas não aumentam `planned_executions`, que sempre é
`planned_pairs × 2`. IDs de experimento, par e execução são determinísticos.

### GET, DTO e estados

`ExperimentResponse.experiment` é `ExperimentDTO` com
`dto_schema_version: "1.0"`, separado de `protocol_version: 1`. Inclui
`manifest_sha256`, referências ao manifesto anual, manifesto congelado,
limitações, pares, tentativas, custos, artefatos com checksums e
`summaries_by_window`; `error_code` pode identificar falha operacional do
worker sem braço ativo (por exemplo, `worker_failed_without_active_attempt`).
Nesse caso `status` pode ser `failed` mesmo com `failed_pairs == 0`; os pares
`queued` continuam contados em `missing_pairs`. Os valores de métrica têm
`value`, `unit`, `period`,
`provenance_kind`, `method_version` e `artifact_sha256`. Proveniência inclui
`synthetic_generated` para demanda, `simulated` para saídas SUMO e `derived`
para deltas/resumos. Filas cobrem `demand_window`; viagens, tempo e velocidade
cobrem `completed_trips_through_drain`.

As referências `arena_manifest_id` e `arena_manifest_sha256` recebidas no POST
são registradas como `caller_asserted_unverified` no manifesto e a limitação
`arena_manifest_reference_unverified` é retornada no DTO. Esta API não consulta
um registro anual imutável para validar essas referências.
O backend sempre preserva `synthetic_aurora`, `window_only`,
`network_aggregated`, `not_causal` e `not_real_world_validated`, mesmo que o
cliente envie uma lista `limitations` vazia. Cada intervenção é aplicada em
memória à entrada congelada de toda janela selecionada para validação antes de
criar ou enfileirar o experimento.
O manifesto fixa `backend_code_sha256`, Python, container, versões instaladas de
FastAPI/Pydantic/Arena/Simulation e versão do adaptador; cada tentativa repete
essas identidades, além das versões e hashes de SUMO/netconvert; a tentativa
registra engine/version quando há resultado. Se os executáveis ou suas versões
não forem identificáveis na criação, o manifesto recebe
`sumo_environment_unavailable` e nenhuma métrica simulada pode ser publicada.
O worker recusa execução e retry com `execution_environment_mismatch` se o
código ou ambiente não corresponder ao manifesto. Crie outro experimento para
executar com uma versão diferente.

O estado geral do experimento é `queued | running | succeeded | partial |
failed | cancelled`. O estado de cada `PairDTO` é
`queued | running | succeeded | failed | cancelled`; os estados de braço e
tentativa são `queued | running | succeeded | failed | cancelled`. `pairs`
sempre mantém todas as linhas da matriz: pares ainda sem execução ficam
`queued`, inclusive os IDs listados em `missing_pair_ids`. Portanto
`missing_pairs` é uma contagem, não uma lista. `failed_pairs` conta pares
`failed` **e** `cancelled`.

Os contadores obedecem
`planned_pairs = completed_pairs + failed_pairs + running_pairs + missing_pairs`.
Um experimento geral pode estar `running` com `running_pairs == 0` durante a
inicialização/retomada do worker; nesse intervalo os pares podem continuar
`queued`. Isso não indica conclusão nem ausência de trabalho.

Resumo e IC são calculados no backend e segregados por janela, estratégia e
métrica. `arm_summary` contém estatísticas separadas de `baseline` e
`strategy`; `paired_delta_summary` usa estratégia menos baseline. Em execução
incompleta, summaries descritivos usam somente pares completos e `selection` é
`complete_pairs_only`; `confidence_interval.lower` e `.upper` ficam nulos para
a janela incompleta. `seed_sensitivity`
e `paired_delta_seed_sensitivity` informam `observed_variation`,
`no_variation_observed` ou `insufficient_data`; ausência de variação não é
alegação de robustez.

### Retry e cancelamento

O retry aceita `{"pair_ids":null}` para tentar todos os pares incompletos, ou
uma lista explícita de IDs (ou `{}` para todos). Só falhas recuperáveis com
tentativas restantes podem ser tentadas novamente; o endpoint rejeita braços
que já atingiram `max_attempts_per_execution`. Braços já `succeeded` mantêm seus
resultados e não são executados de novo; o ordinal da tentativa aumenta no
braço que falhou. Os valores de braço bem-sucedido permanecem em `executions`
para auditoria, mas um par incompleto não recebe `baseline_metrics`,
`strategy_metrics` ou `deltas`. Quando `pair_ids` contém IDs, apenas esses pares
são executados nessa retomada; a seleção fica persistida e vale também após
restart. Omitir `pair_ids` significa retomar todos os pares elegíveis.
Selecionar somente pares já concluídos retorna conflito e não altera o escopo.

O cancelamento usa `POST /api/v1/mobility-experiments/{experiment_id}/cancel`
sem corpo. Se nenhum processo estiver ativo, a resposta fica `cancelled`. Se
SUMO estiver rodando, a resposta mantém estado geral `running` e define
`cancellation_requested: true` até o worker reconhecer o pedido; então o estado
passa a `cancelled`. O cliente deve continuar fazendo polling pelo GET.

O SQLite e os artefatos ficam em `apps/api/.data/` por padrão. Configurações
operacionais podem substituir o caminho com `AURORA_EXPERIMENT_DB` e
`AURORA_EXPERIMENT_DATA`. SUMO continua um avaliador sintético por janela: não
altera estado urbano anual, não gera indicador anual e não deve ser anualizado
nem agregado entre janelas.

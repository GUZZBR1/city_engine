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
Ainda não há fila externa, persistência ou rota de cancelamento.
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

As cinco políticas do benchmark são resolvidas por um registry fechado da API.
Cada instância e proposta inclui `policy_id`, `policy_version` e `policy_sha256`;
o hash identifica a versão, categoria, configuração fixa e implementação registrada.
O cliente não escolhe código, versão ou configuração de política. A Arena mantém
o pipeline de observação congelada, proposta, validação/arbitragem e execução com
commit atômico das cinco instâncias.

Jobs de simulação, comparação e Arena usam memória do processo e
`BackgroundTasks`; reiniciar a API perde os jobs. Não há fila externa,
persistência durável nem rota de cancelamento. A execução da Arena calcula os
modelos anuais de referência e, quando os binários estão disponíveis, executa
comparações SUMO de janela para ações semafóricas aceitas. Essa saída não
representa tráfego observado, validação empírica ou resultado anual.

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

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
`GET /api/v1/comparisons/{comparison_id}`. Jobs ficam em memória neste MVP
local e se perdem quando a API reinicia. Simulações e comparações rodam em
background após a resposta HTTP; ainda não há fila externa, persistência ou
rota de cancelamento.
O POST aceita `drain_limit_seconds` (inteiro entre 0 e 604800; padrão 3600),
que limita o tempo adicional para veículos solicitados terminarem após a janela
de demanda. O job retorna solicitadas, concluídas e não concluídas sem recalcular
as métricas do motor.

Uma comparação aceita os mesmos parâmetros da simulação e uma intervenção
declarativa. O exemplo de Aurora mantém o ciclo em 66 s e altera somente as
durações do controlador `node:02:00`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/comparisons \
  -H 'Content-Type: application/json' \
  -d '{"city_id":"aurora-base-v1","window_id":"weekday_am_peak","seed":42,"drain_limit_seconds":3600,"intervention":{"node_id":"node:02:00","phases":[{"movement":"north_south","duration_seconds":40},{"movement":"all_red","duration_seconds":3},{"movement":"east_west","duration_seconds":20},{"movement":"all_red","duration_seconds":3}]}}'
```

A resposta inicial contém o `comparison_id`; consulte
`GET /api/v1/comparisons/{comparison_id}` até `succeeded` ou `failed`. O
resultado inclui identidades das duas execuções, parâmetros comuns, métricas
originais do motor e deltas intervenção menos base. Se qualquer execução falhar,
a comparação não publica métricas nem deltas parciais. As métricas permanecem
sintéticas e não representam validação empírica. Se nenhuma rota da janela usar
arestas incidentes ao controlador alterado, o resultado traz um aviso de falta
de exposição para contextualizar deltas sem mudança.
O mapa usa `LocalFeatureCollection` em coordenadas cartesianas locais métricas,
nunca GeoJSON RFC 7946.

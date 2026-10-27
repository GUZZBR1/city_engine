# Arquitetura completa — Urban Twin Arena

**Status:** arquitetura de referência v0.1

**Cidade padrão:** [`aurora-base-v1`](../../configs/cities/aurora-base-v1.yaml)

**Conceito de produto:** [Urban Twin Arena](../conceito/urban-twin-arena.md)

**Piloto empírico futuro:** [ficha de reprodução do trânsito observado](../piloto/ficha-piloto.md)

> **Recorte atual do produto:** arena de tráfego e infraestrutura viária. A primeira competição já executa cinco políticas de temporização semafórica no mesmo cruzamento, pareadas contra a mesma base. Este documento mantém contratos de evolução mais amplos; obras, pavimentação, orçamento competitivo e rodovias ainda não fazem parte do modelo executável.

## 1. Decisão executiva

Construir a primeira versão da arena viária como um **monólito modular Python**, com uma aplicação **React + TypeScript** e um **worker de simulação isolado**. O sistema terá contratos estáveis entre rede, estratégias das empresas, modelos de tráfego e adaptadores, mas não começará distribuído em vários microsserviços.

| Responsabilidade | Padrão inicial |
|---|---|
| Domínio, modelos e orquestração | Python |
| API | FastAPI + Pydantic + OpenAPI |
| Interface | React + TypeScript |
| Mapa | MapLibre GL JS 2D |
| Mobilidade | SUMO encapsulado por adaptador |
| Persistência espacial e transacional | PostgreSQL + PostGIS |
| Execução assíncrona | Worker Python; PostgreSQL mantém estado e fila inicial |
| Artefatos grandes | Diretório de artefatos local no MVP; armazenamento de objetos depois |
| Infraestrutura | Docker Compose no desenvolvimento; orquestração maior após benchmarks |

PyTorch, Kaggle, Redis, NATS, TimescaleDB, deck.gl e Kubernetes não são requisitos iniciais. Entram quando uma necessidade funcional, operacional ou de desempenho estiver demonstrada.

## 2. Premissas e fronteiras

- Aurora é benchmark sintético; a ficha de piloto real continua sendo a referência para validação empírica.
- A configuração YAML é a fonte versionada do estado-base; os artefatos do SUMO são derivados e reproduzíveis.
- Agentes propõem ações tipadas. O servidor valida e aplica as ações; agente não escreve diretamente no estado nem chama o SUMO.
- Modelos calculam transições candidatas. O estado da rodada só é confirmado se os modelos e invariantes terminarem sem erro.
- API e web não executam a simulação pesada dentro do processo de requisição.
- Simulações independentes e replicações são paralelizáveis; não se promete paralelização multinó de uma simulação microscópica única.
- Dados observados, sintéticos, estimados e simulados permanecem distinguíveis em armazenamento, API, mapa e relatório.

## 3. Camadas e fluxo principal

| Camada | Componentes | Responsabilidade |
|---|---|---|
| Apresentação | Web React/TypeScript, MapLibre | Configurar experimentos, exibir mapa, andamento e resultados |
| Entrada | FastAPI, autenticação, schemas | Validar requisições, autorizar acesso e criar/consultar recursos |
| Aplicação | Casos de uso e orquestração | Coordenar experimentos, rodadas, jobs, transições e publicação |
| Domínio | Estado da cidade, regras, ações, indicadores | Regras puras e independentes de framework ou simulador |
| Modelos | Mobilidade, finanças e futuros domínios | Calcular mudanças de estado, métricas, diagnósticos e incerteza |
| Adaptadores | SUMO, PostGIS, artefatos, fila | Traduzir contratos do domínio para tecnologias concretas |
| Execução | Worker de simulação e runtime de políticas | Rodar jobs isolados com limites de recursos |
| Evidências | Registro de experimentos e manifestos | Preservar proveniência, versões e resultados reproduzíveis |

### Fluxo de um experimento

1. Usuário seleciona `aurora-base-v1`, cenário, horizonte, referência e políticas.
2. API valida o schema e persiste a especificação e um job idempotente.
3. Worker reivindica o job, fixa versões e cria cópias isoladas do snapshot para políticas e referências.
4. Em cada rodada, o runtime recebe uma observação e devolve propostas de ação tipadas.
5. Árbitro valida orçamento, alvos, limites, conflito e pré-condições; ações aceitas são aplicadas a um estado candidato.
6. Modelos executam suas transições. O modelo de mobilidade compila a rede/demanda para SUMO e executa as janelas especificadas.
7. Validadores verificam balanços e invariantes. A rodada é confirmada atomicamente ou marcada como falha.
8. O avaliador calcula vetores de métricas; worker grava manifestos e resultados.
9. Web acompanha status por SSE e consulta o estado autoritativo na API.

## 4. Linguagens e organização do código

### Linguagens

- **Python** para domínio, dados geoespaciais, modelos, integração SUMO, agentes internos e workers.
- **TypeScript** para interface, schemas de cliente e interação com API.
- **SQL** para migrações, índices, restrições e consultas espaciais/analíticas.
- **YAML/JSON** para configurações declarativas de cidade, cenário, agente e experimento.

Não criar um motor próprio em Rust, C++ ou Go antes de profiling identificar gargalo e provar a necessidade. Fixar versões e lockfiles no scaffold; compatibilidade do SUMO e bindings deve fazer parte da matriz de execução.

### Monorepo inicial

```text
urban-twin-arena/
├── apps/
│   ├── api/                     # FastAPI, autenticação e endpoints
│   └── web/                     # React, TypeScript e MapLibre
├── packages/
│   └── urban_arena/              # pacote Python modular
│       ├── domain/               # entidades, value objects, invariantes
│       ├── application/          # casos de uso e orquestração
│       ├── contracts/            # schemas versionados de API/modelos/agentes
│       ├── city/                 # snapshots e geração sintética
│       ├── network/              # grafo canônico e validação topológica
│       ├── demand/               # geração OD e perfis
│       ├── actions/              # propostas, custo e aplicação
│       ├── models/               # contratos e modelos por domínio
│       ├── simulation/sumo/      # adaptador e ciclo SUMO
│       ├── arena/                # cópias, rodadas e replicações
│       ├── evaluation/           # indicadores, incerteza e Pareto
│       └── persistence/          # repositórios e unidade de trabalho
├── workers/
│   └── simulation/               # claim, execução, heartbeat e publicação
├── configs/
│   ├── cities/                   # inclui aurora-base-v1.yaml
│   ├── scenarios/
│   └── policies/
├── infrastructure/
│   ├── compose/                  # ambiente local
│   └── migrations/               # migrações Postgres/PostGIS
├── tests/
│   ├── unit/
│   ├── contracts/
│   ├── properties/
│   ├── integration/
│   ├── scientific/
│   └── e2e/
└── docs/
```

O pacote Python mantém módulos importáveis em uma direção: `domain` não importa FastAPI, SUMO, SQLAlchemy ou React. Adaptadores dependem de contratos do domínio; interface e API não incorporam cálculos científicos.

## 5. Contratos centrais

Todos os contratos são versionados, validados e serializáveis. IDs de snapshot, modelo, agente, cenário, execução e artefato devem ser estáveis.

| Contrato | Campos essenciais |
|---|---|
| `CitySnapshot` | `snapshot_id`, schema, hash, config de origem, estado por domínio e proveniência |
| `ExperimentSpec` | snapshot, horizonte, cenário, políticas, controles, replicações, sementes e métricas |
| `AgentVersion` | ID/version, runtime confiável, observação permitida, schema de ações e limites de execução |
| `Observation` | experiment/run, snapshot da rodada, observação filtrada, relógio e dados visíveis |
| `ActionProposal` | agente, rodada, lista de ações tipadas, alvos, parâmetros e explicação opcional |
| `ActionValidation` | status, custo calculado, regras avaliadas, rejeições, conflitos e ação aplicada |
| `ModelInput` | estado candidato, cenário, ações aprovadas, intervalo temporal, semente e config do modelo |
| `ModelOutput` | delta de estado, métricas tipadas, diagnósticos, incerteza, manifestos e validade |
| `MetricVector` | métrica, unidade, valor/agregação, intervalo, cobertura, grupo/território e origem |
| `ArtifactManifest` | URI, checksum, tamanho, formato, versão de produtor, execução e classificação de dado |

Exemplo resumido de proposta:

```json
{
  "schema_version": "1.0",
  "agent_version": "rule-based-001",
  "round": 2,
  "actions": [
    {
      "type": "bus_frequency_change",
      "target_id": "route-leste-centro-oeste",
      "parameters": {"headway_minutes": 8}
    }
  ]
}
```

O backend calcula custo e efeitos aceitos; valores de custo enviados pelo agente são ignorados. Schema desconhecido, ação não permitida, unidade incompatível ou alvo ausente produz rejeição explícita.

## 6. Domínio da cidade e modelos científicos

### Fonte de verdade urbana

`aurora-base-v1.yaml` define o estado de partida. A geração produz um `CitySnapshot` com hash canônico. Entidades derivadas incluem distritos, zonas, nós, segmentos, faixas, conversões, sinais, rotas de transporte, serviços, população, domicílios, empregos, orçamento e demanda.

Cada dado carrega `provenance_kind`: `synthetic_config`, `synthetic_generated`, `observed`, `estimated` ou `simulated`. Não inferir infraestrutura ausente como inexistente confirmada. A rede gerada é revisável antes da primeira execução.

### Interface de modelo

Cada domínio implementa uma interface equivalente a:

```text
run_transition(ModelInput) -> ModelOutput
```

Contrato por modelo: `model_id/version`, domínios e métricas cobertas, relógio suportado, schema de entrada/saída, requisitos de dados, validade conhecida, custos de execução e limites. O modelo prepara delta candidato; o orquestrador verifica invariantes e só depois confirma o novo estado.

### Relógios

- Rodada estratégica: um ano sintético.
- Finanças, população e estoque urbano: passo anual quando seus modelos existirem.
- Mobilidade: apenas as janelas configuradas em `aurora-base-v1`, com passos do SUMO e período de aquecimento documentados.
- Não anualizar duas janelas de tráfego para representar todos os dias/viagens sem uma hipótese e evidência separadas.
- Efeitos de obras incluem custo na aprovação, atraso antes da operação e manutenção recorrente.

### Adaptador SUMO

1. Validar grafo canônico, sentidos, faixas, conversões, prioridades e programas de sinal.
2. Compilar um artefato de rede SUMO versionado, sem tornar `.net.xml` a fonte de verdade.
3. Gerar rotas/demanda da janela, com semente e parâmetros congelados.
4. Executar processo SUMO isolado; usar modo em lote quando não for necessário controle passo a passo.
5. Usar TraCI para controle externo interativo. Considerar libsumo somente após benchmark e validar diferenças de API/paralelismo.
6. Recolher fluxos, tempos, filas, chegadas e emissões estimadas; guardar os arquivos brutos e métricas agregadas.
7. Registrar veículos que não chegaram, teleporte, perdas, erro de rota e outras exclusões na interpretação.

SUMO documenta o núcleo de simulação como uma execução por processo e limitações de paralelismo distribuído; escalar primeiro **replicações independentes**, não uma cidade microscópica única. [FAQ do SUMO](https://sumo.dlr.de/docs/FAQ.html), [TraCI](https://sumo.dlr.de/userdoc/TraCI/), [libsumo](https://sumo.dlr.de/docs/Libsumo.html). Fixar a versão do SUMO e dos bindings no manifesto de execução.

### Domínios futuros

Adicionar habitação/uso do solo, demografia, finanças, economia, serviços e ambiente individualmente. Cada domínio precisa de balanços explícitos (estoque/fluxo, capacidade, custo, atraso), dados ou parâmetros de benchmark, invariantes e validação própria. Integração entre modelos exige teste adicional; validade isolada não prova validade do sistema acoplado.

## 7. Demanda, cenários e benchmark

A configuração atual define compartilhamento modal de viagens de trabalho como proxy nacional, mas isso não basta para produzir uma demanda executável. O MVP deverá adicionar, com rótulo sintético:

- geração de viagens por população/emprego e finalidade;
- matriz origem-destino entre zonas, com viagens externas;
- horários de saída e perfis por janela;
- ocupação de veículos e regra de conversão de pessoas em veículos;
- tráfego de carga, se incluído;
- versão, faixa, distribuição e semente de cada parâmetro.

Manter conjuntos `development`, `validation_synthetic` e `held_out` separados. Casos de resposta conhecida testam software e invariantes. Benchmarks sintéticos comparam estratégias dentro das regras. Validação sobre cidade real usa observações independentes.

## 8. Agentes e execução segura

### Runtime

- No MVP, executar apenas políticas internas confiáveis: `no_action`, regra fixa e políticas desenvolvidas pelo projeto.
- O agente consome uma observação tipada e devolve uma proposta tipada por stdin/stdout ou chamada interna versionada.
- Não fornecer acesso direto ao banco, artefatos de outros agentes, segredos, shell, API administrativa ou rede externa.
- Estabelecer limites por proposta e rodada: tempo, memória, tamanho de payload, número de ações e tokens/iterações quando aplicável.
- Se futuramente rodar código de terceiros, usar isolamento de processo/container com rede e segredos negados, limites de recursos e sandbox de segurança mais forte; Docker isolado não é garantia suficiente para código adversarial.

### Fairness do experimento

Cada agente recebe a mesma classe de observações, orçamento, regras, ferramentas e limite computacional. Versão e instruções ficam congeladas por competição. Aprendizado entre rodadas é experimento separado e declarado.

PettingZoo é voltado a vários agentes no mesmo ambiente; cinco agentes administrando cópias independentes de Aurora podem começar com um contrato próprio `Observation → ActionProposal`. Gymnasium pode ser avaliado caso seja adotado aprendizado por reforço em ambiente de agente único/cópia. Essas bibliotecas não são dependências do MVP. [Gymnasium API](https://gymnasium.farama.org/v1.0.0/api/env/), [PettingZoo Parallel API](https://pettingzoo.farama.org/1.24.0/api/parallel/).

## 9. Arena, estado e comparação

Cada execução cria cópias independentes de `aurora-base-v1`, uma por agente, mais uma referência sem ação e uma política fixa. Estado de uma cópia nunca vaza para outra.

No MVP local, uma comparação controlada de temporização pareia a base e uma
intervenção declarativa com uma única entrada carregada: mesmo hash de
snapshot, janela, viagens expandidas, semente e limite de escoamento. A
intervenção demonstrativa altera somente as durações de `node:02:04` para
`40, 3, 20, 3` s, preservando o ciclo base de 66 s e o restante do estado. O
resultado publica as métricas originais dos dois motores e deltas intervenção
menos base; falha em qualquer run invalida a comparação e não publica métricas
parciais. Isso demonstra execução pareada de dados sintéticos, não validação
empírica nem score agregado. A janela de pico da manhã inclui rotas que passam
por `node:02:04`; `route_exposure` só é `not_exposed` quando o arquivo completo
e consistente confirma ausência de uma transição pelo nó. Arquivo ausente ou
inválido deixa a exposição como `unknown`.

Por benchmark, congelar snapshot, dados, regras, cenários, parâmetros, agentes, versão do SUMO, ambiente, sementes e métricas. Comparar com cenários e sementes pareados em várias replicações. Persistir a semente por subsistema e as viagens exógenas, não apenas uma semente global.

O árbitro executa ações como transação:

1. validar schemas, alvos, capacidade, orçamento e regras;
2. rejeitar ou resolver conflito com prioridade determinística documentada;
3. calcular custos a partir do catálogo controlado pelo servidor;
4. aplicar as ações num estado candidato;
5. executar modelos;
6. validar conservação de fluxo e balanços de orçamento/população/estoques;
7. confirmar estado e eventos da rodada atomicamente.

Resultados são vetores multidimensionais por cenário, replicação, distrito e grupo. Restrições são mostradas como violações, não compensadas por outro indicador. Pareto é padrão; score composto exige pesos definidos antes da execução e análise de sensibilidade.

## 10. Persistência e artefatos

### PostgreSQL/PostGIS — fonte de verdade operacional

Guardar estado de jobs e experimentos, metadados, snapshots, geometria canônica, ações, eventos, métricas agregadas e manifestos. Entidades/tabelas iniciais:

- `projects`, `users`, `memberships` (quando houver multiusuário);
- `cities`, `city_snapshots`, `districts`, `zones`, `network_nodes`, `network_edges`, `signals`, `facilities`;
- `datasets`, `experiment_specs`, `agent_versions`, `experiment_participants`;
- `simulation_jobs`, `replicates`, `rounds`, `action_proposals`, `action_decisions`;
- `model_runs`, `metric_values`, `artifact_manifests`, `audit_events`.

Snapshot/configuração imutável identifica o estado inicial; estado de rodada registra versão e delta/eventos. Medir consultas antes de normalizar ou desnormalizar em excesso.

### Artefatos grandes

SUMO pode produzir arquivos de rotas, tripinfo, edge/queue outputs, trajetórias e logs científicos. No início, usar volume local dedicado. Evoluir para armazenamento compatível com objeto se tamanho, compartilhamento ou recuperação justificarem. Banco guarda URI, checksum, formato, produtor, política de retenção e execução associada.

Parquet é apropriado para resultados tabulares grandes quando análises justificarem. Não armazenar trajetórias completas se métricas agregadas bastarem. Aplicar backup, retenção e teste periódico de restauração antes de produção.

### Tecnologias adiadas

- **NATS:** quando polling/claim por Postgres não suportar volume ou topologia de workers; se adicionado, adotar transactional outbox para evitar dual-write.
- **Redis:** quando cache demonstrar ganho mensurável; não é fonte autoritativa de job.
- **TimescaleDB:** quando consultas temporais comprovarem necessidade; começar com PostgreSQL.
- **Object storage/MinIO:** quando volume e operação justificarem; usar interface abstrata de artefato.
- **Kubernetes:** quando operação multitrabalhador exigir scheduler e isolamento que Docker Compose não entregue.

## 11. API e contratos HTTP

API versionada em `/api/v1`. Pydantic valida payloads e FastAPI publica OpenAPI. OpenAPI serve como contrato de cliente TypeScript e documentação. [FastAPI — OpenAPI](https://fastapi.tiangolo.com/tutorial/metadata/).

| Método e rota | Uso |
|---|---|
| `GET /api/v1/cities` | Listar cidades acessíveis |
| `GET /api/v1/cities/{city_id}/snapshots` | Listar snapshots imutáveis |
| `GET /api/v1/cities/{city_id}/map` | Buscar geometria e camadas resumidas |
| `POST /api/v1/experiments` | Criar especificação em rascunho |
| `POST /api/v1/experiments/{id}/validate` | Validar dados, regras, custo estimado e elegibilidade |
| `POST /api/v1/experiments/{id}/runs` | Enfileirar execução com `Idempotency-Key` |
| `GET /api/v1/runs/{id}` | Consultar estado autoritativo e progresso |
| `POST /api/v1/runs/{id}/cancel` | Solicitar cancelamento cooperativo |
| `GET /api/v1/runs/{id}/events` | Receber progresso via SSE e retomar com cursor |
| `GET /api/v1/runs/{id}/metrics` | Ler métricas, incerteza e filtros de grupo/distrito |
| `GET /api/v1/runs/{id}/artifacts` | Consultar manifestos e downloads autorizados |

`POST /runs` retorna rapidamente `202 Accepted`, `run_id`, status inicial e link de consulta. WebSocket fica para uma necessidade bidirecional; SSE cobre progresso. `BackgroundTasks` do processo web não executa jobs científicos pesados; API e worker são processos separados. [FastAPI — background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

## 12. Jobs, falhas e idempotência

### Estados

```text
created → validating → queued → claimed → running → publishing → completed
                                  ↘ failed
                                  ↘ cancel_requested → cancelled
```

### Regras operacionais

- PostgreSQL é a fonte de verdade do MVP para job, lease, heartbeat e progresso.
- `Idempotency-Key` impede duplicar execução por retry HTTP.
- Worker reivindica job atomicamente, registra lease/heartbeat e pode recuperar job cuja lease expirou.
- Retentativas são limitadas, com backoff e classificação entre falha transitória e falha determinística.
- Cancelamento é cooperativo; worker termina subprocessos do run e marca artefatos parciais como não publicados.
- Cada replicação concluída pode ter checkpoint interno; resultados só ficam visíveis como completos quando o manifesto final é gravado atomicamente.
- Publicação valida checksums e associação a config/modelo/semente antes de concluir.
- A estimativa de custo cresce com agentes × cenários × sementes × rodadas × replicações; validar quota e permitir cancelamento antes de execuções caras.

## 13. Frontend e mapa 2D

### Navegação

- **Experimentos:** rascunhos, fila, execuções concluídas, canceladas ou com falha.
- **Cidade:** snapshot, distritos, rede, serviços e camadas de proveniência.
- **Configuração:** cenário, agentes, horizonte, replicações, métricas e resumo revisável.
- **Execução:** estado do job, rodada, replicações, eventos e falhas recuperáveis.
- **Comparação:** mapa por métrica, séries por rodada, distribuição entre sementes, custos e efeitos por bairro/grupo.

### Componentes

`AppShell`, `ExperimentWizard`, `CityMap`, `LayerPanel`, `TimeWindowSelector`, `ActionProposalForm`, `ValidationPanel`, `RunStatusPanel`, `ComparisonWorkspace`, `EvidenceBadge` e `ProvenanceDrawer`.

MapLibre exibe geometria e resultados retornados pelo backend; navegador não calcula score, custos finais, regras ou transições científicas. GeoJSON por URL atende Aurora; dividir dados/tilear quando benchmarks mostrarem excesso de volume. [MapLibre — dados grandes](https://maplibre.org/maplibre-gl-js/docs/guides/large-data/). MapLibre GL JS v6 é ESM; manter bundler do frontend compatível. [MapLibre — migração v5→v6](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/).

Estados visuais mantêm rótulos **sintético, observado, estimado, simulado e validado**, sempre com texto e ícone além de cor. Mapa tem tabela/resumo acessível equivalente, teclado, foco visível, contraste e preferência por redução de movimento. Animação de tráfego é complementar aos indicadores.

## 14. Segurança e governança

### MVP local

- Políticas internas confiáveis; sem execução de código de terceiros.
- API valida todas as ações no servidor.
- Limites por job para CPU, memória, duração, disco, processos e tamanho de artefato.
- Dados e segredos não entram em prompt/logs; trajetórias sensíveis não são logadas.
- Uploads geográficos ficam fora do MVP.

### Antes de uso externo/multiorganização

- OIDC/OAuth, RBAC e autorização server-side em cada snapshot, job, métrica e artefato.
- Isolamento por `organization_id`/`project_id`; não confiar em IDs fornecidos pelo cliente.
- Namespace de objetos por tenant, links de download curtos e autorização antes de emitir URL.
- Auditoria de mudanças, acesso, execuções e exportação.
- Quotas por projeto e limites contra negação de serviço por payload ou replicações.
- Política LGPD: finalidade, minimização, agregação, retenção e exclusão para dados de mobilidade.
- Ao habilitar arquivos: limite de bytes/feições, validação CRS/geometria, proteção contra zip-bomb/path traversal e parser isolado.

## 15. Observabilidade e manutenção

- Logs estruturados com `request_id`, `experiment_id`, `run_id`, `replicate_id`, `round` e versões; sem dados sensíveis.
- Métricas: jobs por estado, duração por modelo, CPU/memória, retries, cancelamentos, falhas, tamanho dos artefatos, custo por replicação e latência da API.
- Traces OpenTelemetry atravessam API, claim do worker, submodelos e publicação.
- Alertas posteriores para job sem heartbeat, falha repetida de worker, disco cheio e divergência de manifestos.
- Painel inicial pode começar com logs e métricas essenciais; Prometheus/Grafana entra conforme ambiente operacional.

## 16. Implantação por estágio

| Estágio | Implantação |
|---|---|
| Desenvolvimento | Docker Compose: web, API, PostgreSQL/PostGIS e worker; volume local para artefatos; SUMO instalado/pinado na imagem do worker |
| Protótipo compartilhado | API e workers em containers separados, Postgres gerenciado/backup, armazenamento de objetos se necessário |
| Produção multiusuário | OIDC, isolamento por tenant, quotas, backup/PITR, fila durável conforme carga, observabilidade e restauração testada |
| Escala de experimentos | Escalar réplicas de worker por benchmark; particionar uma simulação única somente após pesquisa e teste de fronteira |

## 17. Qualidade e verificação

| Tipo | Alvo |
|---|---|
| Unitário | Custos, validação de ações, agregação de métricas, transições e permissões |
| Contrato | Schemas API, Observation/ActionProposal, ModelInput/Output e migrações |
| Propriedades | Soma de população/empregos, orçamento, fluxo, capacidade, grafo conectado e transições válidas |
| Integração | Geração Aurora → compilação SUMO → execução → extração de métricas |
| Reprodutibilidade | Mesmo snapshot, config, versão e seed gera artefatos equivalentes dentro da tolerância declarada |
| Científico | Dados sintéticos conhecidos, validação empírica holdout, métricas e limites por domínio |
| Falhas | Job expirado, worker reiniciado, retry duplicado, cancelamento, publicação parcial e recuperação |
| Segurança | Acesso cruzado, payload inválido, limite de recursos e parsers de arquivos quando habilitados |
| E2E | Gerar cidade → configurar → executar → comparar → exportar relatório |

Uma rodada só é aceita se os invariantes e schemas passarem. Critérios científicos e limiares de validação real são definidos antes de acessar o conjunto holdout.

## 18. Roadmap técnico

1. **MVP 0 — Configuração e cidade:** validar YAML, gerar snapshot e geometria canônica, calcular hash e criar cinco cópias idênticas.
2. **MVP 1 — Mapa:** servir distritos/rede como GeoJSON e visualizar Aurora com etiquetas de dado sintético.
3. **MVP 2 — Mobilidade:** fechar parâmetros de demanda, compilar rede para SUMO, rodar janelas, guardar outputs e métricas.
4. **MVP 3 — Experimentos:** API e job lifecycle, uma política sem ação, uma política fixa, replicações e comparação.
5. **MVP 4 — Ações:** semáforo, frequência de ônibus e manutenção com custo, validação e transação de rodada.
6. **MVP 5 — Arena de agentes:** cinco políticas internas, sandbox, cenários pareados, incerteza e Pareto.
7. **MVP 6 — Validação empírica:** escolher cidade real por dados/licença, calibrar e validar mobilidade com observações independentes.
8. **Fases futuras:** adicionar domínios urbanos, benchmark com topologias reservadas, multiusuário e escala operacional.

### Gate para avançar

- Aurora → SUMO: topologia e demanda determinísticas, rede compilada validada e run reproduzível.
- SUMO → Arena: métricas tipadas, custo/ações, state machine e baseline funcionando.
- Arena → alegação comparativa: replicações, cenário comum, intervalos de incerteza e política de referência.
- Sintético → cidade real: fonte autorizada, cobertura adequada, dados independentes, protocolo congelado e validade delimitada.
- Cada novo domínio: balanço, unidade, período, contrato de troca, validação e limites declarados.

## 19. Decisões em aberto

1. Fixar geometria, conectividade, faixas, conversões e regras semafóricas exatas de `aurora-base-v1`.
2. Fixar algoritmo de demanda OD, taxa de geração, partidas, ocupação e tráfego externo sintéticos.
3. Definir schemas formais e convenção de versionamento.
4. Definir política determinística de resolução de ações conflitantes.
5. Definir número de replicações após medir variabilidade e efeito mínimo de interesse.
6. Definir retenção/formato de trajetórias e artefatos brutos.
7. Selecionar versões concretas de Python, SUMO, FastAPI, PostgreSQL/PostGIS, React, TypeScript e MapLibre no scaffold, após validar compatibilidade e suporte.
8. Especificar agentes não confiáveis e modelo de isolamento antes de habilitar código enviado por usuários.

## 20. Revisão de especialistas

Esta arquitetura integra cinco revisões: desenho do sistema, contratos científicos, pesquisa de documentação oficial, experiência frontend e segurança/operação. A conclusão comum é manter fronteiras explícitas, começar simples e medir antes de distribuir.

Fontes técnicas oficiais consultadas:

- [SUMO FAQ](https://sumo.dlr.de/docs/FAQ.html), [TraCI](https://sumo.dlr.de/userdoc/TraCI/), [libsumo](https://sumo.dlr.de/docs/Libsumo.html), [tempo de simulação](https://sumo.dlr.de/docs/Simulation/Basic_Definition.html), [TripInfo](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html), [filas](https://sumo.dlr.de/docs/Simulation/Output/QueueOutput.html), [aleatoriedade](https://sumo.dlr.de/docs/Simulation/Randomness.html).
- [FastAPI/OpenAPI](https://fastapi.tiangolo.com/tutorial/metadata/) e [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
- [Gymnasium](https://gymnasium.farama.org/v1.0.0/api/env/) e [PettingZoo Parallel API](https://pettingzoo.farama.org/1.24.0/api/parallel/).
- [MapLibre GL JS — grandes dados](https://maplibre.org/maplibre-gl-js/docs/guides/large-data/) e [migração para v6](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/).

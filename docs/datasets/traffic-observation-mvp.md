# Auditoria e mini-MVP de observações de tráfego

**Data da auditoria:** 2026-10-27
**Escopo:** quatro datasets Kaggle prioritários, contrato canônico, adapter CSV, replay local e API.
**Status científico:** exploratório/sintético; nenhuma fonte abaixo autoriza calibração empírica de Aurora.

## Resultado executivo

O City Engine começa com um `CitySnapshot` Aurora determinístico, imutável e explicitamente sintético. A API existente lê metadados/mapa e executa SUMO com `SimulationInput`; ainda não existe pipeline independente para observações históricas, store de tráfego ou replay.

Os quatro candidatos não reduzem a dependência de dados sintéticos: três são descritos como gerados/simulados; no quarto, os dados de linha não foram acessados e a descrição trata cidades fictícias. **Não há aqui observações rodoviárias verificadas.** Para exercitar a arquitetura, o mini-MVP usa apenas o dataset 1 como fixture sintético, isolado de Aurora e do SUMO. Isso prova o caminho de software, não adiciona evidência empírica.

### Decisão

- **Adapter demonstrativo:** dataset 1, `traffic_sensor_data.csv`.
- **Classificação por registro:** `simulated`.
- **Permitido:** ingestão, validação de schema, replay e teste da API.
- **Proibido:** escrever em `CitySnapshot`, mapear para as arestas de Aurora, calcular demanda SUMO, calibrar/validar SUMO ou alegar previsão de trânsito real.
- **Dados brutos:** não são versionados no repositório. A API lê uma cópia local obtida pelo Kaggle CLI.

## Diagnóstico do repositório antes da mudança

| Área | Estado encontrado |
|---|---|
| Cidade | `packages/urban_arena` gera snapshot hashado a partir de YAML; geometrias em `synthetic_local_cartesian_m`. |
| Demanda e SUMO | `packages/simulation` consome `SimulationInput` de rede/demanda. Não deve conhecer CSVs de observação. |
| API | FastAPI oferece mapa, metadados, simulação e competição pareada. Não havia endpoints de observações ou replay. |
| Persistência | Jobs e estado existentes são locais/em memória. Não há Postgres, Event Stream ou store de observações. |
| Frontend | Interface mostra Aurora sintética. Este mini-MVP é API-first e não altera mapa/estado visual da cidade. |
| Governança | Conceito e ficha do piloto exigem proveniência, dados independentes e separação entre exploração sintética e validação empírica. |

## Auditoria dos datasets

Os auditores usaram a CLI configurada do Kaggle para inventariar arquivos e, quando viável, examinaram arquivos completos ou amostras. “Desconhecido” abaixo significa que o arquivo não pôde ser lido; não significa que o problema não exista.

### 1. Smart City Traffic Flow Prediction Dataset

[Página Kaggle](https://www.kaggle.com/datasets/rauffauzanrambe/smart-city-traffic-flow-prediction-dataset) · Proveniência declarada pela página/configuração: tráfego “simulado” ou inspirado em condições reais. Sem provedor rastreável, método de coleta ou vínculo verificável com a organização citada. Classificação: **simulated / mixed-claim, not field-validated**. Kaggle declara Apache-2.0; licença e direitos de eventuais fontes subjacentes não foram verificados.

| Arquivo | Conteúdo auditado |
|---|---|
| `traffic_sensor_data.csv` | 218.400 × 15; 50 sensores; 4.368 timestamps de meia em meia hora por sensor; 2024-01-01 00:00 a 2024-03-31 23:30; timestamps sem fuso. Colunas: `timestamp`, `sensor_id`, `location`, `direction`, `vehicle_count`, `average_speed_kmh`, `occupancy_rate`, `congestion_level`, `car_count`, `motorcycle_count`, `truck_count`, `bus_count`, `day_of_week`, `is_holiday`, `hour`. |
| `weather_conditions.csv` | 21.840 × 11; 10 estações horárias; temperatura, umidade, precipitação, vento, visibilidade, UV, pressão, AQI e tipo climático. Estações sem coordenadas ou join documentado com sensores de tráfego. |
| `traffic_events.csv` | 2.000 × 15; tipo/severidade, via, início/fim, duração, resposta, vítimas, descrição, causa e condição climática. Campos de tipo/descrição/causa têm combinações contraditórias. |
| `road_network.csv` | 200 × 18; IDs de vias, geometria por coordenadas inicial/final, comprimento, faixas, velocidade, capacidade e atributos. Não forma um SUMO network pronto. |
| `road_network_international.csv` | 1.401 × 41; atributos de vias em 20 cidades/países, com unidades/moedas locais. É outro conjunto, não extensão da rede de Jakarta. |
| `sensor_locations.json` | 50 objetos; IDs, coordenadas declaradas WGS84, nome, status, direção de cobertura, taxa declarada, road segment, distrito e informações IoT. |
| `traffic_prediction_config.json` | Configuração de features/modelos/treino/deployment; não são predições nem saídas reprodutíveis. Métricas declaradas não vêm acompanhadas de resultados ou protocolo reproduzível. |

**Qualidade verificada no arquivo completo:** sem células vazias nem linhas duplicadas; sem duplicatas nas chaves `(sensor_id,timestamp)` e `(station_id,timestamp)`. 107/218.400 linhas têm `vehicle_count` diferente da soma das categorias. A série tem 30 min, mas o metadata declara amostragens de 30–300 s. O sensor metadata aponta 50 sensores e 42 road IDs; o teste espacial reportado pelo auditor encontrou todos os sensores a mais de 1 km do segmento atribuído (média de cerca de 15,3 km). Só aparecem `Low` e `Medium`, embora a configuração declare quatro classes. Na meteorologia, 4.550/21.840 precipitações são negativas (mínimo −2 mm). Eventos têm campos semânticos conflitantes. Dados cobrem 50 sensores/um trimestre e não incluem viagens, rotas, OD, densidade ou séries de previsão materializadas.

**Serve para:** parser/CSV, schema, validações de série temporal, testes de API/replay sintéticos. **Não serve para:** estado empírico, calibração/validação SUMO, demanda OD, perfil horário de uma cidade real, forecasting operacional, densidade (ocupação não é densidade), anomalias/acidentes reais ou benchmark científico. O projeto usa somente o CSV de tráfego; coordenadas/road IDs são preservados, quando presentes, como metadata não verificado. Clima e eventos são excluídos por falta de join confiável e problemas semânticos.

### 2. Urban traffic density in cities

[Página Kaggle](https://www.kaggle.com/datasets/tanishqdublish/urban-traffic-density-in-cities) · Kaggle lista `futuristic_city_traffic.csv` (100.075.737 bytes) e declara licença MIT. Descrição anuncia mais de 1,2 milhão de registros e seis cidades fictícias. O download falhou durante a auditoria por erro de resolução de `api.kaggle.com`; **nenhuma linha foi examinada**.

A página anuncia 11 campos: cidade, tipo de veículo, clima, condição econômica, dia/horário, velocidade, consumo de energia, pico, evento aleatório e densidade. Nomes exatos, tipos, row count, missingness, duplicatas, outliers e valores reais do CSV são **desconhecidos**. Não há datas, timezone, coordenadas, IDs de rua/sensor, fluxo/contagem, viagens ou OD documentados. Consumo é descrito como estimado. Há conflito entre a descrição de cidades fictícias e trabalhos externos que chamam a base de real; esses artigos não substituem a inspeção do arquivo.

**Serve para:** somente um demo sintético tabular após obter e auditar o arquivo. **Não serve para:** state/replay observado, SUMO, demanda, perfis temporais reais, calibração, validação de modelos ou claims de densidade urbana real. Faltam localização, datas e amostragem que permitam ligação à cidade. Leakage não pôde ser verificado; `Traffic Density` é o alvo anunciado e consumo é derivado de tipo/velocidade, portanto há risco de circularidade.

### 3. CityFlow: Smart Urban Mobility and Traffic IoT

[Kaggle](https://www.kaggle.com/datasets/mobeenfatimah/cityflow-smart-urban-mobility-and-traffic-iot) · [Gerador](https://github.com/MobeenFatimaa/Smart-city-traffic-Urban-Mobility-dataset-Generator/blob/main/generate_dataset.py) · [Dicionário](https://github.com/MobeenFatimaa/Smart-city-traffic-Urban-Mobility-dataset-Generator/blob/main/datadictionary.md). O CSV tem 204.000 × 47 linhas/colunas: 100 interseções × 2.040 horas, de 2026-01-01 00:00 a 2026-03-26 23:00, timestamps sem fuso. 94 `road_id`s; cinco IDs são associados a mais de uma interseção. Coordenadas são jitter sintético em torno de Nova York, sem geometria/topologia viária.

Colunas: `record_id`, `city_zone`, `road_id`, `intersection_id`, `latitude`, `longitude`, `road_type`, `lanes`, `speed_limit`, `vehicle_count`, `average_speed`, `heavy_vehicle_count`, `motorcycle_count`, `public_transport_count`, `traffic_density`, `queue_length`, `average_wait_time`, `timestamp`, `hour`, `day_of_week`, `is_weekend`, `is_holiday`, `rush_hour`, `peak_period`, `temperature`, `rainfall_mm`, `visibility_km`, `air_quality_index`, `weather_condition`, `nearby_school`, `nearby_hospital`, `nearby_market`, `construction_activity`, `road_condition`, `parking_occupancy`, `public_event`, `accident_reported`, `traffic_camera_count`, `iot_sensor_health`, `signal_cycle_seconds`, `green_light_duration`, `emergency_vehicle_detected`, `traffic_flow_rate`, `congestion_score`, `emission_estimate`, `fuel_waste_estimate`, `congestion_level`.

**Qualidade completa:** sem ausentes/duplicatas; IDs únicos; horários e flags derivados consistentes; `traffic_flow_rate` replica `vehicle_count`; densidade e congestionamento são fórmula/threshold do gerador; combustíveis/emissões são estimativas algébricas. 29.885 linhas excedem o parâmetro nominal `lanes × 600`; filas/espera têm caudas altas. `congestion_level` depende de `congestion_score`, que usa velocidade, densidade e fila: usar estas features para prever o rótulo no mesmo instante seria leakage/circularidade. `is_holiday` é aleatório. Valores meteorológicos variam independentemente por interseção/hora.

É sintético, não observado, nem demanda OD; não há trajetórias ou câmera. **Serve para:** demonstração sintética de pipelines ricos e análise com holdout temporal e espacial. **Não serve para:** estado de cidade, replay histórico real, calibração/validação SUMO, benchmark empírico, OD ou claims de acidente/emissão real. Licenças conflitantes: metadata Kaggle CC BY-NC-SA 4.0, texto da descrição CC BY 4.0 e repositório MIT para o software gerador. Reuso dos dados fica bloqueado até esclarecer.

### 4. AetherGrid Smart Mobility Data (50K)

[Página Kaggle](https://www.kaggle.com/datasets/shanza30/aethergrid-smart-mobility-data-50k). Um CSV com 50.000 × 14, auditado integralmente. Colunas: `user_id`, `trip_id`, `start_lat`, `start_lon`, `end_lat`, `end_lon`, `distance_km`, `speed_kmh`, `traffic`, `weather`, `vehicle_type`, `timestamp`, `day_of_week`, `is_weekend`. 50.000 IDs únicos de usuário/viagem; horário ingênuo de 2025-01-01 00:00 a 2025-01-31 00:00; 29.608 minutos distintos. Nenhum timezone declarado.

Publisher declara simulação Python; Kaggle declara CC0, sem fontes upstream/metodologia/calibração. Não há contagem de fluxo, densidade, segmento, rota, evento, sensor ou medição meteorológica. **Qualidade completa:** sem ausentes/duplicatas; todos os timestamps e números parseáveis; weekday/weekend derivam corretamente do timestamp. Todos os starts, mas 15.350 destinations ficam fora do bounding box Karachi anunciado. Em 45.680/50.000 viagens, `distance_km` é menor que a separação geodésica entre endpoints, fisicamente incompatível se o campo for comprimento de viagem.

**Serve para:** teste sintético de parser de trip e conversão de endpoints em edges, apenas para testar o pipeline. **Não serve para:** estimar demanda OD, calibrar/validar SUMO, replay real, perfil temporal, congestionamento/densidade ou validação de previsão. IDs e campos de calendário podem causar leakage; split aleatório também mistura registros com timestamps repetidos. Não há base para mapear coordenadas para Aurora.

## Ranking e usos permitidos

O ranking é **para iniciar o pipeline**, não para representar qualidade científica:

| Rank | Dataset | Uso permitido | Razão/limite |
|---:|---|---|---|
| 1 | #1 Smart City Traffic Flow | Adapter/replay de fixture e validação de contrato. | Tem painel completo sensor×tempo e contagem/velocidade, mas provenance simulada, unidades incompletas e join espacial falho. |
| 2 | #3 CityFlow | Demo sintética rica, depois de licença esclarecida. | Dados íntegros e documentados pelo gerador, mas alvos/feature são circulares e não há geometria; licença conflita. |
| 3 | #4 AetherGrid | Smoke test de viagens sintéticas. | Endpoints e timestamp existem, mas geometria/distância e área conflitam; não é OD real. |
| 4 | #2 Urban Traffic Density | Demo tabular eventual, depois de baixar/auditar. | CSV inacessível; sem datas/localização/IDs de via confirmados. |

| Capacidade | #1 | #2 | #3 | #4 |
|---|---|---|---|---|
| Estado de gêmeo observado | Não | Não | Não | Não |
| Replay histórico como **observação real** | Não | Não demonstrado | Não | Não |
| Replay de fixture sintético | Sim, MVP | Só após auditar CSV | Sim, com licença resolvida | Sim, smoke test |
| Calibrar/validar SUMO | Não | Não | Não | Não |
| Demanda OD real | Não | Não | Não | Não |
| Teste de conversor de demanda | Sem rotas/OD | Não | Não | Sim, sintético e com ressalvas |
| Ajustar perfis horários reais | Não | Sem datas/ordem | Não | Não; timestamp irregular/sintético |
| Forecast/ML científico | Não | Não | Não; leakage direto | Não |
| Benchmark científico externo | Não | Não | Não | Não |

Logo, **não se conectam esses quatro ao SUMO para calibração, validação ou demanda empírica**. Contagens/velocidades precisam de proveniência, unidade, associação sensor→edge e validação independente antes de qualquer comparação.

## Contratos e arquitetura do mini-MVP

```text
Kaggle CSV / futuro CSV, JSON, Parquet, DB, API, MQTT, WebSocket ou sensor
  → ObservationSource adapter
  → TrafficObservation (schema 1.0 + provenance_kind)
  → ReplaySession
  → ObservationStore (in-memory neste MVP; interface substituível)
  → traffic-state overlay versionado por replay
  → Models
  → Simulation Engine (não ligado neste MVP)
  → Evaluation (não ligada neste MVP)
```

O pacote `packages/traffic_observations` não importa FastAPI, SUMO ou UI. API depende do pacote; SUMO não conhece Kaggle. `CitySnapshot` Aurora permanece imutável. O endpoint retorna uma **materialização de observações por replay**, não escreve no estado de cidade nem declara que sensor pertence a Aurora.

`TrafficObservation` é tipado e serializável. Campos centrais são opcionais se não existirem; nenhum valor é preenchido por imputação. Cada evento leva `schema_version`, `observation_id`, `observation_type`, timestamp, source/dataset/location IDs, road/intersection IDs, coordenadas, count/flow/speed/density, congestion/weather/event, confidence, `provenance_kind` e `metadata`.

Mapeamento do dataset #1:

| Contrato canônico | Mapeamento do CSV | Decisão |
|---|---|---|
| `observation_id` | `dataset_id:sensor_id:timestamp` | Determinístico; repetir o mesmo arquivo gera os mesmos IDs. |
| `source_id`, `location_id` | `sensor_id` | Identificador de sensor de origem, não um ID de sensor de Aurora. |
| `vehicle_count` | `vehicle_count` | Preservado; não corrige os 107 desacordos com categorias. Metadata marca as linhas incoerentes. |
| `mean_speed_kmh` | `average_speed_kmh` | Mapeado pela unidade explícita no nome do campo. |
| `congestion_level` | rótulo da fonte | Preservado como categoria sem validação operacional. |
| `flow_veh_h`, `density` | — | `None`; intervalos/unidade e geometria não bastam para calcular. Ocupação fica em `metadata`. |
| `latitude`, `longitude`, `road_segment_id` | sensor JSON | Mantidos como metadata reportada; não promovidos a campos canônicos devido à falha do join espacial. |
| clima, acidentes, eventos | — | Excluídos do adapter: estações sem associação, chuva negativa e rótulos de evento inconsistentes. |
| `confidence` | — | `None`; a fonte não informa confiança por linha. |

Proveniência `simulated` segue em cada linha e no manifesto. Manifesto traz URL, artefato, hash SHA-256, licença declarada como não verificada e limitações; o adapter recalcula o hash antes de cada leitura para rejeitar arquivo alterado desde a criação do manifesto. Timestamp continua sem fuso; o sistema não o converte para UTC.

## Replay e API

Replay cria sessão pausada e lê o CSV em ordem timestamp/sensor; verifica ordenação e ordena caso necessário. Filtros temporais e por `location_id` estão habilitados. Filtro de região retorna 422 para este dataset porque não há coordenadas canônicas verificadas; o contrato aceita bounding boxes para fontes futuras que comprovem coordenadas. Tipo de observação é filtrável no core; fonte inicial emite apenas tráfego.

Controles: `pause`, `resume`, `reset`, `step` (1–10.000 observações) e `set_speed` (eventos por segundo). O store mantém a última observação por sensor para cada replay. O registry é limitado a 100 sessões: ao atingir o limite, descarta a sessão não ativa mais antiga; se todas estiverem rodando, retorna erro de capacidade. É em memória e se perde quando API reinicia; ainda não há Event Stream durável. Em múltiplos workers, cada processo teria um registry distinto; produção requer store/job backend compartilhado.

Rotas adicionadas:

- `POST /api/v1/traffic-replays` — cria replay pausado da fonte configurada; não recebe path arbitrário.
- `GET /api/v1/traffic-replays/{replay_id}` — status, filtros, proveniência, hash e estado materializado.
- `GET /api/v1/traffic-replays/{replay_id}/state` — overlay atualizado por sensor.
- `POST /api/v1/traffic-replays/{replay_id}/controls` — aplica uma operação de replay.

Arquivo não é versionado. Baixe os artefatos em diretório local ignorado por Git e configure o diretório da API:

```bash
mkdir -p data/external/smart-city-traffic
kaggle datasets download rauffauzanrambe/smart-city-traffic-flow-prediction-dataset \
  --file traffic_sensor_data.csv --path data/external/smart-city-traffic --unzip
kaggle datasets download rauffauzanrambe/smart-city-traffic-flow-prediction-dataset \
  --file sensor_locations.json --path data/external/smart-city-traffic --unzip
kaggle datasets download rauffauzanrambe/smart-city-traffic-flow-prediction-dataset \
  --file traffic_prediction_config.json --path data/external/smart-city-traffic --unzip
export CITY_ENGINE_TRAFFIC_DATA_DIR=data/external/smart-city-traffic
```

O endpoint exige somente o CSV; JSON de sensores/config é opcional e seus valores vão para metadata não verificada.

## SUMO: plano de calibração e validação

**Não realizado:** nenhum dataset foi ligado ao `SimulationInput`. A geometria de Aurora é local cartesiana, enquanto #1 declara WGS84; o sensor→segmento do próprio pacote falha spatial QA; não há OD observado; `vehicle_count` tem janela/unidade sem evidência suficiente. Converter visualmente ou usar nomes de ruas como edges seria inventar correspondência.

Etapas quando houver uma fonte empírica apropriada:

1. Definir local/período e rede de referência; verificar licença, cobertura, timezone, unidade, método de coleta e IDs de detector/edge.
2. Resolver sensor→edge com critério espacial/revisão e registrar incerteza; separar contagem/velocidade de demanda e não inferir OD unicamente de contagens.
3. Separar período de calibração e holdout independente por tempo e, quando possível, por trecho/corredor. Congelar parâmetros antes do holdout.
4. Comparar por segmento e intervalo: GEH/erro de volume; MAE/RMSE de velocidade/tempo; MAPE só para observado positivo, não próximo de zero; erro de fila/densidade somente se medições correspondentes existirem. Reportar viés, cobertura, resíduos e intervalos de incerteza.
5. Não tratar mapa parecido, contagem visual ou ajuste em dados de treino como validação.

## ML versus SUMO

Forecast ML: observações passadas → features disponíveis no instante → previsão de count/speed para horizonte declarado. `train < validation < test` no tempo; holdout por sensor/segmento para generalização espacial; remover IDs/variáveis derivadas que vazem o alvo; ajustar transformação só no treino; reportar baseline e métricas por horizonte/segmento. `traffic_prediction_config.json` do #1 declara resultados e pipeline, mas não traz previsões materializadas nem protocolo reproduzível, então esses scores não são evidência.

SUMO permanece modelo causal/operacional: rede + cenário/demanda + controles → execução → métricas. ML não substitui SUMO. O MVP atual não implementa previsão nem cálculo de calibração.

## Mini-MVPs e critérios

| MVP | Status | Entrada → saída | Aceite/teste |
|---|---|---|---|
| A. Auditoria | Concluído para cards/arquivos acessíveis; #2 sem conteúdo | Quatro pacotes → ficha, rank e claims permitidos | Lacunas ficam “desconhecidas”, sem imputação |
| B. Canonical `TrafficObservation` | Implementado | Campos de origem opcionais → contrato schema 1.0/proveniência | Valida coordenadas parciais, ranges, optionalidade e JSON |
| C. Adapter #1 | Implementado | CSV + sidecars opcionais → eventos simulados ordenados | Schema estrito, conversão de speed, ID determinístico, hash e flags; sem colunas fictícias |
| D. Replay | Implementado | Iterator fonte + filtros → sequência controlada | Pause/resume/reset/step/speed, timer determinístico e filtros testados; bbox rejeitado quando fonte não valida espaço |
| E. Observation Store | Implementado, in-memory | Eventos → última observação por sensor | Estado determinístico e limpeza no reset; persistência futura independente |
| F. API/City State overlay | Implementado | Replay → API overlay por dataset | OpenAPI, status e controles; teste confirma Aurora snapshot continua sintético e sem mutação |
| G. Calibração SUMO | Bloqueado por evidência | Rede+observação real → parâmetros calibrados | Exige dados espaciais reais, unidade e protocolo/holdout; nenhum candidato passou |
| H. Forecasting | Adiado | Observações → previsão | Exige observações verificadas, split temporal e baseline; separar do SUMO |
| I. Anomalia/densidade/OD | Adiado | Medidas compatíveis → estimador | Exige definição operacional, labels/ground truth e/ou viagens amostradas |

Os MVPs A–F não importam conteúdo direto no SUMO. G–I permanecem independentes e não bloqueiam o teste do contrato/replay.

## Agentes e evidências

O Master mapeou a arquitetura, escolheu o escopo e integrou as mudanças. Quatro agentes de pesquisa trabalharam em paralelo, um por dataset; pesquisa não implementou código. Um reviewer independente conduziu cinco rodadas: apontou validação CSV, limite do registry, teste do timer, dados temporários, sidecar inválido, caminhos locais, corrida em callbacks, integridade de hash e codificação; as correções foram feitas e testadas. A quinta rodada concluiu **PASS, sem achados concretos remanescentes**, confirmando também que Aurora fica sintética e o dataset não se conecta ao SUMO.

| Agente | Objetivo/entrada | Saída principal | Hipóteses/limitações |
|---|---|---|---|
| Dataset Auditor 1 | Kaggle #1; CLI, metadados e sete artefatos | Auditoria completa das cinco CSVs e dois JSONs; 218.400 sensor rows; 107 count mismatches; joins espaciais falham | Nenhuma provenance por registro; classificação simulada/real-world-inspired sem medição provada. Task `city-engine-dataset-deep-audit-01-20261027`. |
| Dataset Auditor 2 | Kaggle #2; metadata e mirror | Uma listagem de 100 MB, cidades fictícias e campos anunciados; download falhou, row-level QA desconhecida | Zero linhas inspecionadas; artigos externos contraditórios não são prova. Task `...deep-audit-02-20261027`. |
| Dataset Auditor 3 | Kaggle #3, CSV completo e gerador | 204k×47, sem nulos/duplicatas; métricas derivadas/leakage; conflito de licença | Alto suporte a “sintético”, nenhum suporte a cidade real; Task `...deep-audit-03-20261027`. |
| Dataset Auditor 4 | Kaggle #4, CSV completo | 50k×14, sem nulos/duplicatas; 15.350 destinos fora do limite; distância incompatível em 45.680 linhas | Publisher declara simulador; sem demanda observada. Task `...deep-audit-04-20261027`. |
| QA/Scientific reviewer | Revisões independentes do código, contrato, API e claims científicos | Rounds 1–4 encontraram pontos médios/baixos; correções cobertas por regressões. Round 5: PASS, sem achados remanescentes. | Revisão do diff e auditorias; a suíte foi executada pelo Master. Tasks `city-engine-traffic-mvp-review-round1` a `city-engine-traffic-mvp-review-round5-20261027`. |

### Limites científicos transversais

Possíveis vieses: cobertura urbana declarada não verificada; geração balanceada e regular; ausência de sensores offline; timezone ausente; categorias/rótulos e unidades pouco definidos; IDs/flags codificam target ou ordem; datasets com coordenadas sem rede validada. Split aleatório pode vazar tempo/entidade; alvo calculado de features torna avaliação circular.

### Riscos técnicos e próximos passos

- O arquivo #1 não acompanha o repositório; API retorna 503 até configurar diretório local.
- Store/replay são em memória/processo; sem recuperação, concorrência multiworker, retenção ou stream durável.
- Metadados de coordenada/road ID são preservados como reportados, mas não promovidos a localização canônica.
- Licença Kaggle é declaração de uploader; nenhuma redistribuição de dados foi feita.
- Melhor próximo passo científico: buscar contagens/speed observations com fonte primária, licença, timezone, unidade e rede de uma área real identificável; #1 serve só como smoke fixture até lá.
- Melhor próximo passo técnico: Event Store durável e adapter de uma fonte real atrás do mesmo contrato, sem mexer no SUMO até passar gates de rede e cobertura.

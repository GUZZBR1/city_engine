# Especificação do estado da cidade — v1

**Status:** contrato documental para o estado inicial de Aurora e sua evolução futura.
**Cidade de referência:** `aurora-base-v1`, sintética.
**Fonte de valores atuais:** [`configs/cities/aurora-base-v1.yaml`](../../configs/cities/aurora-base-v1.yaml).

Esta especificação distingue o que o repositório já carrega e valida do que é somente desenho. Aurora não é uma cidade observada nem um gêmeo digital empírico. As referências do IBGE são proxies para parâmetros explicitamente indicados; não transformam a cidade ou seus outros atributos em dados reais.

## 1. Estado de implementação

| Parte | Situação no repositório |
|---|---|
| Configuração inicial | Implementada em YAML com `schema_version: 1`; modelos Pydantic estritos, congelados e validação de balanços em `packages/urban_arena`. |
| Snapshot inicial | Implementado como projeção determinística do YAML. A projeção de primeiro nível é reduzida; `source_config` preserva a configuração YAML completa. O snapshot também contém identidade, versões, proveniência sintética, totais selecionados, distritos, mobilidade e camadas geométricas locais. |
| Geometria e rede | Distritos, nós e arestas direcionadas são gerados deterministicamente; capacidade, classe e velocidade das vias vêm da configuração. Espaço local cartesiano em metros, não coordenadas geográficas. |
| Entrada do simulador | Contrato tipado implementado para rede, sinais, demanda, janela e semente. A execução de simulação é tratada nos pacotes/API próprios. |
| Hash | SHA-256 do payload canônico do snapshot, calculado antes de acrescentar `hash` e `snapshot_id`. |
| Cópias | `create_agent_copies` cria cinco cópias profundas independentes para o valor configurado atual, com o mesmo hash inicial. Não há, nessa função, evolução de rodada nem isolamento transacional completo garantido para estruturas internas mutáveis. |
| Evolução anual da cidade | Proposta arquitetural. Não há implementação de transições anuais acopladas para habitação, demografia, finanças públicas, emprego/economia, serviços, ambiente ou qualidade de vida. |
| Estado persistido e eventos de evolução | Proposta; a configuração e a geração local do snapshot não constituem persistência de histórico de estados. |

O snapshot inicial é tratado como imutável por contrato e serve como identidade de entrada. Embora os modelos Pydantic sejam configurados como congelados, estruturas aninhadas incluem coleções mutáveis; portanto, o código atual não garante imutabilidade profunda. Um resultado de modelo não deve editar o snapshot inicial no lugar: a transição futura recebe um estado-base e produz um novo estado versionado ou um delta validado.

## 2. Identidade, schema e versionamento

### Identificadores observados

- `city.id`: `aurora-base-v1` — identidade do perfil configurado.
- `schema_version`: `1` no YAML; serializado como string no `CitySnapshot`.
- `generator_version`: `0.3.0` no gerador atual.
- `snapshot_id`: `<city_id>:<sha256>`; identifica o conteúdo inicial, não uma rodada futura.
- `hash`: 64 caracteres hexadecimais minúsculos, SHA-256 do payload canônico.

### Regra de evolução do contrato

`schema_version` identifica a estrutura e semântica do documento de configuração/snapshot; `generator_version` identifica o algoritmo que deriva o snapshot. Mudança incompatível de campos, unidades ou significado requer nova versão maior de schema e migração explícita. Mudança compatível pode acrescentar campos opcionais sem reinterpretar existentes. A migração deve declarar origem, destino, transformações e validação; nunca deve preencher lacunas com observações inventadas. A versão do modelo de domínio e a versão do cenário também devem ser identificadores próprios, separados do schema e do gerador.

Para evolução, recomenda-se identificar cada estado por `(city_id, parent_snapshot_id, round_index, transition_id)` e calcular um hash novo sobre o estado candidato validado. O hash inicial permanece referenciável como raiz. Esse identificador de estado evolutivo ainda é **proposto**, não está implementado pelo gerador atual.

## 3. Domínios e campos atuais

Onde a primeira coluna indica um caminho, ele é relativo à raiz do YAML. Linhas agrupadas podem resumir mais de um campo, identificados pelo nome completo. Unidades são explicitadas quando fazem parte do nome/contrato; para quantidades sem unidade dimensional, a tabela diz “contagem” ou “fração”. Valores são do arquivo atual e, onde marcado, derivados por cálculo descrito no próprio arquivo.

### 3.1 Identidade e geografia

| Caminho | Valor atual | Unidade / interpretação | Proveniência |
|---|---:|---|---|
| `city.id`, `city.name` | `aurora-base-v1`, `Aurora` | identificadores/texto | desenho sintético |
| `city.status` | `synthetic_benchmark` | classificação | sintético |
| `city.country_reference` | `BR` | referência contextual, sem localização | referência de benchmark |
| `city.census_reference_year` | `2022` | ano de referência | fontes de contexto |
| `urban_footprint.area_km2` | `36` | km² | parâmetro de projeto, não média nacional |
| `urban_footprint.geometry` | `square_6km_by_6km` | forma abstrata | sintético |
| `urban_footprint.urban_resident_density_per_km2_derived` | `1633` | residentes/km² | derivado, arredondado |
| `mobility.network.grid_intersections` | `[5, 5]` | colunas × linhas de cruzamentos | sintético |
| `mobility.network.directed_edges_derived` | `74` | arestas direcionadas | derivado da grade e barreira |
| `mobility.network.arterial_corridors` | `2` | contagem | sintético |

A geometria efetivamente produzida usa `synthetic_local_cartesian_m`. Seus limites são derivados de 36 km² em um quadrado local de 6.000 × 6.000 m; não codificam latitude/longitude.

### 3.2 População e distritos

| Caminho/campo | Valor atual | Unidade / interpretação | Proveniência |
|---|---:|---|---|
| `population.total_residents` | `67.250` | residentes | média aritmética de municípios no recorte operacional 20.000–500.000 do Censo 2022, aplicada como referência sintética |
| `population.statistical_basis` | município; faixa `[20.000, 500.000]`; amostra `1.668`; soma `112.172.687`; média `67.249,8` | municípios / residentes | fonte IBGE; proxy declarada, não mediana |
| `population.household.mean_residents_per_occupied_household` | `2,79` | residentes/domicílio ocupado | média nacional IBGE 2022 |
| `population.household.occupied_households_derived` | `24.104` | domicílios ocupados | derivado de população / média nacional |
| `population.urban_rural.urban_share_reference`, `rural_share_reference` | `0,8741`, `0,1259` | fração da população | participação nacional IBGE 2022, não específica do recorte |
| `population.urban_rural.urban_residents_derived`, `population.urban_rural.rural_catchment_residents_derived` | `58.783`, `8.467` | residentes | derivações do total e participações de referência |

| Distrito (`id`) | Tipo | Residentes | Empregos | Uso do solo configurado |
|---|---|---:|---:|---|
| `centro` | urban | 8.817 | 12.000 | administration_commerce_services_transit |
| `norte_residencial` | urban | 17.635 | 1.500 | residential_schools_local_services |
| `sul_misto` | urban | 14.696 | 3.500 | residential_commerce_health |
| `leste_logistico` | urban | 5.878 | 6.000 | logistics_light_industry |
| `oeste_verde` | urban | 11.757 | 1.000 | low_density_residential_park_protected_area |
| `entorno_rural` | external_catchment | 8.467 | 0 | rural_origin_destination_zone |

Empregos por distrito e `employment.total_jobs: 24.000` são hipótese sintética de benchmark, não resultado de inferência populacional nem estatística municipal. População e empregos são contagens de referência do estado inicial; grupos por idade/renda/mobilidade reduzida e dinâmica demográfica não estão definidos no YAML atual.

### 3.3 Emprego, mobilidade e demanda

| Caminho/campo | Valor atual | Unidade / interpretação | Proveniência |
|---|---:|---|---|
| `employment.total_jobs` | `24.000` | empregos localizados | hipótese sintética |
| `mobility.network.road_classes.local` | 40 km/h; 1 faixa; 600 veículos/h | velocidade, faixas, capacidade agregada por aresta direcionada | hipótese sintética |
| `mobility.network.road_classes.collector` | 50 km/h; 1 faixa; 900 veículos/h | idem | hipótese sintética |
| `mobility.network.road_classes.arterial` | 60 km/h; 2 faixas; 1.800 veículos/h | idem | hipótese sintética |
| `mobility.network.barrier` | orientação `north_south`, 2 travessias | contagem; `arterial_bridge`, `lower_capacity_collector` | hipótese topológica sintética |
| `mobility.network.traffic_signals` | `node:02:00`, offset 0 s; `node:02:04`, offset 31 s; programa `aurora-synthetic-fixed-v1` | s; cada ciclo: NS 35 s, all-red 3 s, EW 25 s, all-red 3 s | plano sintético fixo, sem calibração |
| `mobility.transit` | 1 rota: leste_logistico → centro → oeste_verde; intervalos 10/20 min | rotas; minutos entre ônibus no pico/fora de pico | hipótese sintética; não é uma linha empiricamente modelada |
| `mobility.commute_main_mode_share` | automóvel .323; ônibus .214; a pé .178; motocicleta .164; bicicleta .062; outros .059 | fração, soma 1 | proxy nacional entre trabalhadores que se deslocam ao trabalho, não todas as viagens |
| `mobility.simulation_windows` | `weekday_am_peak` 07:00–09:00; `weekday_off_peak` 11:00–13:00 | horários representativos, sem fuso especificado | períodos sintéticos, não horários observados |
| `mobility.demand.seed` | `42` | semente inteira não negativa | padrão de execução |
| `mobility.demand.generation_method` | fluxos OD fixos por arco e janela | taxas constantes em veículos/h durante janela | benchmark sintético; sem inferência de viagens reais, ocupação ou conversão modal |

Fluxos OD atuais em `mobility.demand.windows[].od_flows[]` (todos `passenger`, origem/destino são nós da grade; cada item marca `synthetic: true` e uma hipótese):

| Janela | ID | De → para | veículos/h |
|---|---|---|---:|
| manhã | `am-od-001` | `node:01:00` → `node:01:04` | 180 |
| manhã | `am-od-002` | `node:03:00` → `node:03:04` | 120 |
| manhã | `am-od-003` | `node:00:02` → `node:04:02` | 90 |
| manhã | `am-od-004` | `node:04:04` → `node:00:04` | 75 |
| fora de pico | `off-od-001` | `node:01:00` → `node:01:04` | 90 |
| fora de pico | `off-od-002` | `node:03:00` → `node:03:04` | 60 |
| fora de pico | `off-od-003` | `node:00:02` → `node:04:02` | 45 |
| fora de pico | `off-od-004` | `node:04:04` → `node:00:04` | 38 |

As taxas são veículos por hora por fluxo OD, não pessoas/h nem contagem observada. As janelas não são anualizadas. A participação modal de trabalho não é regra de geração desses fluxos.

A rota e os intervalos de ônibus são declarativos na configuração/snapshot; o `SimulationInput` atual não os inclui como oferta de transporte simulada.

### 3.4 Finanças e arena

| Caminho/campo | Valor atual | Unidade / interpretação | Proveniência |
|---|---:|---|---|
| `finance.currency` | `simulated_urban_credits` | unidade de jogo, sem conversão para BRL | economia normalizada sintética |
| `finance.credits_per_round` | 100 | créditos/rodada | hipótese de jogo |
| `finance.fixed_operations`, `finance.reserve`, `finance.discretionary_budget` | 60, 10, 30 | créditos/rodada | alocação configurada |
| `arena.round_duration` | `one_synthetic_year` | um ano sintético por rodada | escala do experimento, não calendário previsto |
| `arena.default_horizon_rounds` | 10 | rodadas | padrão experimental |
| `arena.ai_agent_copies` | 5 | cópias iniciais | quantidade configurada |
| `arena.reference_policies` | `no_action`, `fixed_rule` | políticas | referências de benchmark |
| Resumo das flags `arena.initial_state_immutable`, `common_random_scenarios`, `paired_replicates_required`, `default_scoring`, `universal_single_score` | estado inicial tratado como imutável; cenários aleatórios comuns; replicações pareadas; painel multidimensional/Pareto; sem score universal | protocolo | contrato de experimento |

O orçamento atual não descreve receita, dívida, caixa real ou despesas de serviços. A evolução financeira contábil por rodada é proposta, não implementada.

## 4. Domínios evolutivos previstos

O contrato arquitetural prevê os domínios abaixo. Só os elementos identificados na seção 3 existem no estado/configuração atuais; os demais campos são **propostas de domínio**, sem valores de Aurora a completar por suposição.

| Domínio | Campos/saídas propostos | Relógio proposto | Situação |
|---|---|---|---|
| Geografia e uso do solo | distritos, zonas, geometrias locais, classe/função, áreas protegidas, restrições e versão | estático por snapshot; alterações por ação | distritos e rede local implementados em forma reduzida; zonas, zoneamento formal e áreas como entidades não implementados |
| Demografia | residentes por zona e grupo, nascimentos, mudanças, migração | uma transição por rodada/ano sintético | total e partição urbana/entorno inicial; dinâmica e grupos ainda não implementados |
| Habitação | estoque de unidades, capacidade, ocupação, custo de construção/manutenção e preço sintético | anual | somente domicílios agregados derivados; estoque e transição propostos |
| Emprego e atividades | empregos por setor/zona, horários, capacidade e vacância | anual | empregos agregados por distrito configurados; setor/atividade e dinâmica propostos |
| Mobilidade | grafo, modos, transporte, demanda OD, janelas, capacidade e métricas de execução | janelas de simulação; agregação anual não presumida | rede, semáforos, ônibus declarativo, proxies modais e demanda fixa configurados; simulação-base descrita nos pacotes existentes |
| Serviços | localização, capacidade, área de atendimento, utilização e demanda não atendida | anual ou frequência do serviço declarada | apenas menções ilustrativas nos usos de solo; inventário/capacidade não configurados |
| Finanças públicas | caixa, receitas, despesas recorrentes, manutenção, orçamento, dívida | anual | apenas economia de créditos do jogo; contabilidade urbana proposta |
| Ambiente | áreas verdes, emissões estimadas e limites explícitos do cenário | por janela e/ou anual | `oeste_verde` no uso do solo; nenhum inventário ou modelo ambiental configurado |
| Qualidade de vida/equidade | indicadores derivados por território/grupo, cobertura e método | depois dos domínios de entrada | catálogo conceitual; sem valores/índice no snapshot atual |
| Regras | zoneamento, orçamento, níveis mínimos de serviço, limites e ações autorizadas | por versão de cenário/rodada | restrições de esquema e jogo parciais; regras urbanísticas completas propostas |

Todo novo campo deve declarar tipo, unidade, faixa válida, resolução espacial, relógio, proveniência, versão/modelo produtor, estado de ausência e se é observado, derivado, inicializado ou simulado. Indicadores derivados não devem ser editáveis diretamente por agentes.

## 5. Proveniência e semântica dos valores

O YAML atual registra `provenance.synthetic_city: true` e `empirical_validation_status: not_validated_against_real_city_observations`. As quatro entradas em `provenance.sources` devem continuar associadas somente ao uso declarado:

- `ibge_census_2022_population_classes` — média municipal no recorte populacional operacional.
- `ibge_census_2022_household_size` — moradores por domicílio ocupado.
- `ibge_census_2022_urban_rural_share` — participações urbanas/rurais de referência.
- `ibge_census_2022_commuting_modes` — proxy modal principal para trabalhadores que se deslocam ao trabalho.

No snapshot, camadas geradas identificam `provenance_kind: synthetic_generated`; distritos da configuração identificam `synthetic_config`; a proveniência geral é `synthetic`. Arquitetura propõe o vocabulário `synthetic_config`, `synthetic_generated`, `observed`, `estimated` e `simulated`. `observed` não pode ser atribuído a Aurora sem incorporação posterior de observação real independente e metadados de origem/licença. Parâmetros sem uma fonte empírica específica permanecem hipótese sintética.

Para um estado evolutivo futuro, cada atributo deve poder apontar para: valor; unidade; proveniência/tipo; fonte ou artefato; transformação; modelo e versão; data/intervalo de validade; incerteza/cobertura quando aplicável. Um valor ausente deve ser `unknown`/nulo com motivo, não zero nem inexistência presumida.

## 6. Faixas e invariantes

### Validações existentes

- Modelos de configuração usam `extra="forbid"` e são congelados; quantidades configuradas de velocidade, faixa, capacidade, taxa OD e duração de fase têm limites positivos, semente/offset não negativos.
- IDs de distritos, janelas, semáforos e fluxos OD são únicos nos seus escopos; grupos de schema e rótulos de movimento são limitados por enums.
- Residentes urbanos e do entorno fecham com seus totais derivados; soma de residentes distritais fecha com a população total; empregos distritais fecham com empregos totais.
- Participações urbana+rural e participações modais somam 1; operações fixas+reserva+discricionário fecham com os créditos por rodada.
- Grade tem ao menos 2 linhas/colunas; arestas direcionadas correspondem à grade menos trechos bloqueados pela barreira; número de travessias e tipos fecha; cada tipo tem classe viária.
- Semáforo aponta para nó existente, tem fases NS e EW, offset dentro do ciclo e índice inicial válido.
- Cada janela de simulação tem exatamente uma configuração de demanda; horários são `HH:MM` válidos e fim posterior ao início. Cada OD tem nós válidos, origem diferente do destino e ID único na janela.
- Cópias solicitadas devem ser pelo menos uma. O atual é cinco.

### Invariantes para transições propostas

Ao adicionar novos domínios, validar em estado candidato antes de confirmar a rodada: não negatividade e limites do schema; unidades compatíveis; conservação explícita de estoques/fluxos quando o modelo os define; soma de grupos igual ao total correspondente; balanços financeiros; capacidades e restrições territoriais; IDs estáveis e referências existentes; relógios e intervalos sem sobreposição indevida; integridade da proveniência; e fechamento dos indicadores derivados a partir das fontes declaradas. Cada invariante deve dizer a regra, escopo, tolerância numérica e tratamento de ausência. Não se deve impor balanço inventado onde a semântica não o define.

## 7. Hash, determinismo e cópias independentes

Implementação atual (`generate_snapshot`):

1. Valida e carrega a configuração YAML tipada.
2. Gera os elementos derivados deterministicamente; ordena chaves no JSON, usa separadores compactos, UTF-8, `ensure_ascii=False` e rejeita NaN.
3. Calcula SHA-256 sobre o payload do snapshot antes de adicionar os próprios campos `hash` e `snapshot_id`.
4. Acrescenta `hash` e `snapshot_id = city_id:hash`.

O payload inclui a versão de schema como texto, `generator_version`, conteúdo de origem, valores normalizados, camadas e espaço de coordenadas. Logo, uma alteração de conteúdo incluído muda a identidade; mudanças no algoritmo devem atualizar `generator_version`. O hash atesta identidade byte-semântica do payload canônico, não verdade factual, validade científica ou equivalência do modelo. O snapshot atual não inclui um hash de executáveis externos nem prova a integridade de arquivos de execução posteriores.

`create_agent_copies` faz `model_copy(deep=True)` cinco vezes: cada cópia parte do mesmo snapshot e mantém o mesmo `snapshot_id`/hash inicial. A independência é conceitual e por objetos profundos separados; os modelos congelados não tornam automaticamente imutáveis todas as listas/dicionários aninhados. Até que existam transições, persistência e proteção de mutabilidade testadas, não declarar isolamento operacional completo.

Na evolução proposta, cada cópia mantém seu próprio estado e histórico de eventos. A transição deve ser pura sobre a entrada, produzir candidato separado e só publicar estado após validar invariantes. Cópias comparadas recebem o mesmo snapshot-base, cenário exógeno, parâmetros e sementes pareadas conforme o protocolo, mas nenhuma alteração de uma cópia pode vazar para outra. Uma intervenção produz identidade/hash próprios e registra o hash ancestral, diff, ação, modelo/versão e semente. Preservar a referência ao snapshot inicial e não reescrevê-lo.

## 8. Critérios de aceite desta especificação

- [x] Identifica Aurora e mantém explícito que toda a cidade é sintética e ainda não validada por observações reais.
- [x] Separa campos e capacidades existentes das propostas de evolução.
- [x] Registra os valores atuais relevantes da configuração com nomes, unidades e proveniência; taxas OD e faixas não foram convertidas em observações.
- [x] Define responsabilidade de schema/gerador/modelo, hash canônico e identificação do snapshot evolutivo proposto.
- [x] Documenta invariantes implementadas e regras necessárias antes de confirmar transições futuras.
- [x] Descreve a igualdade do estado inicial e independência requerida das cópias, incluindo a limitação atual de mutabilidade aninhada.
- [x] Revisões somente de leitura por `architect` e `verifier` concluídas; ajuste editorial sobre imutabilidade profunda aplicado, sem outros achados pertinentes.

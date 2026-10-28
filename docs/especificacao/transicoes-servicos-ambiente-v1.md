# Transições anuais de serviços e ambiente — v1

**Status:** proposta para a primeira fatia anual demonstrativa; não implementada nem validada empiricamente.

**Escopo:** regras configuráveis para capacidade/demanda de escola e atenção primária, área verde pública explícita e emissões estimadas de atividade veicular anual explicitamente informada. Não altera a configuração canônica de Aurora nem atribui significado ambiental observado aos rótulos de uso do solo.

## 1. Base factual e convenções

O YAML atual fornece população municipal e residentes por distrito, incluindo cinco distritos urbanos e o entorno rural, além da área urbana modelada. O total municipal é 67.250; os cinco distritos urbanos somam 58.783 e o entorno externo tem 8.467. Há uma rodada por ano sintético. Não há contagem de estudantes, demanda de saúde, instalações, capacidade de serviços, polígonos de áreas verdes, atividade veicular anual ou inventário de emissões.

`land_use` é um rótulo funcional textual. `residential_schools_local_services`, `residential_commerce_health` e `low_density_residential_park_protected_area` não provam a existência/localização de escola, unidade de saúde, parque, área protegida ou qualquer área mensurável. Nenhuma transição abaixo deve derivar estoque ou resultado ambiental desse campo.

Na referência integrada `feature-aurora-round-engine`, o catálogo de indicadores estabelece os cálculos SER-02/SER-03 e AMB-01/AMB-03, mas o código de rodadas ainda não implementa transições anuais de domínio nem publica esses indicadores. Esta especificação detalha uma fatia proposta, não descreve comportamento disponível.

Rótulos de proveniência usados neste documento:

- `synthetic_config`: hipótese escrita na configuração, sem alegação empírica.
- `simulated`: saída de regra/modelo executada sobre entradas versionadas.
- `estimated`: estimativa dependente de fator e atividade especificados; não é medição.
- `derived`: transformação determinística identificada, preservando a proveniência das entradas.
- `observed`: reservado a medição ou registro empírico com fonte, período, cobertura e licença apropriados. Não é usado nos defaults propostos.

Ausência de insumo produz `null` e motivo (`missing_input`, `unknown_coverage` ou `not_applicable`, conforme o caso); nunca se converte em zero. Os valores de demonstração abaixo são hipóteses sintéticas, não estatísticas brasileiras, padrões legais ou previsão para uma cidade real.

## 2. Relógio, população e estado anual

Uma rodada `r` corresponde ao ano sintético `r`, iniciando no snapshot imutável do ano 0. Cada modelo anual executa uma vez por rodada, seguindo a ordem de transição definida pelo orquestrador. Os serviços usam o último estado populacional comprometido disponível. Até existir modelo demográfico, a população por distrito permanece constante; se futura transição demográfica mudar a população, essa saída versionada alimenta a rodada seguinte. Não estimar idades ou elegibilidade a partir de atributos que o snapshot não possui.

Na primeira fatia, resultados de escola e saúde abrangem somente os cinco distritos urbanos com denominadores explícitos. O entorno rural fica `null` para esses serviços até que sejam declaradas sua área de captação, elegibilidade, capacidade e regra de alocação. Não chamar o resultado urbano de cobertura municipal.

### 2.1 Hipóteses configuráveis para demonstração

Os defaults a seguir permitem testar o cálculo sem fingir dados observados. Cada valor e a respectiva versão devem persistir no manifesto do experimento.

| Parâmetro | Default demonstrativo | Unidade e interpretação |
|---|---:|---|
| `school.eligible_share` | 0,18 | estudantes elegíveis por residente, hipótese sintética uniforme por distrito |
| `school.initial_seats_per_resident` | 0,16 | vagas disponíveis por residente na data inicial, hipótese sintética uniforme |
| `health.annual_visits_per_resident` | 2,4 | demanda teórica de consultas por residente/ano, hipótese sintética uniforme |
| `health.initial_visits_per_resident_year` | 2,0 | capacidade anual inicial de consultas por residente, hipótese sintética uniforme |
| `green.public_area_m2_per_resident` | centro 2; norte 4; sul 3; leste 1; oeste 8 | m² públicos elegíveis por residente urbano; hipótese sintética por distrito, não extraída do nome do distrito |
| `emissions.annual_vehicle_km_per_resident` | 2.500 | veículo-km por residente urbano/ano sintético, atividade exógena sintética, não derivada das janelas SUMO |
| `emissions.co2e_kg_per_vehicle_km` | 0,18 | kg CO₂e por veículo-km; fator demonstrativo sintético, não fator oficial nem medido |

Os valores numéricos são somente fixtures iniciais para exercitar unidades, fórmulas e desagregação. Devem ser substituíveis, ter limites configuráveis e carregar `provenance_kind: synthetic_config` e uma descrição explícita da hipótese. Não criar escolas/unidades individuais nem acesso geográfico a partir deles: a fatia opera com agregados distritais.

## 3. Regras de serviços

### SER-02a — Demanda anual de vagas escolares não atendida

- **Estado/entradas:** residentes por distrito; `eligible_share`; estoque de vagas iniciais e alterações de capacidade com rodada efetiva. Não há grupo etário observado.
- **Unidades:** demanda e volume atendido em estudantes/vagas por ano letivo; capacidade em vagas/ano letivo; déficit também em vagas/ano letivo.
- **Inicialização:** `D[d,0] = residents[d,0] × eligible_share`; `C[d,0] = residents[d,0] × initial_seats_per_resident`. Esses defaults são hipóteses sintéticas, inclusive quando multiplicados por população configurada com referência estatística.
- **Transição anual:** `C[d,r] = C[d,r−1] + commissioned_seats[d,r] − retired_seats[d,r]`. Acréscimos só entram na rodada efetiva configurada; sem evento de entrada/baixa, a capacidade é constante. `D[d,r] = residents[d,r] × eligible_share`. Sem entrada populacional nova, usar população constante do último estado.
- **Alocação local v1:** `served[d,r] = min(D[d,r], C[d,r])`; `unmet[d,r] = max(0, D[d,r] − C[d,r])`; `unmet_pct[d,r] = 100 × unmet[d,r] / D[d,r]`. Se `D=0`, percentual é `null/not_applicable`; volume não atendido é zero somente quando a demanda zero é explicitamente conhecida.
- **Parâmetros e limites:** `eligible_share ∈ [0,1]`; capacidades, adições e baixas são números não negativos em vagas/ano letivo. Validar `retired_seats ≤ C[d,r−1] + commissioned_seats`; limites de capacidade total são configuráveis por cenário e não existem defaults legais. Capacidade não pode ficar negativa.
- **Desagregação:** distrito urbano e total dos distritos urbanos, calculado somando numeradores e denominadores antes da razão. O total municipal, o entorno rural, idade, renda, gênero e qualidade da escola ficam indisponíveis sem entradas próprias. Não tirar média simples das porcentagens distritais.
- **Incerteza e interpretação:** elegibilidade, capacidade nominal, arredondamento e alocação são incertos; mostrar parâmetros e cenário. O cálculo não modela qualidade, presença, matrícula, preferência, deslocamento, lotação intranual nem aluno único. Chamá-lo de demanda atendível por capacidade, não de acesso geográfico nem atendimento observado.
- **Proveniência:** residentes vêm do snapshot sintético; parâmetros e capacidades iniciais são `synthetic_config`; estado anual e atendimento teórico são `simulated`; razões são `derived` sobre entradas identificadas. Nenhum valor é `observed`.

### SER-02b — Demanda anual de atenção primária não atendida

- **Estado/entradas:** residentes por distrito; `annual_visits_per_resident`; capacidade anual de consultas e alterações versionadas. Uma pessoa pode gerar múltiplas consultas; demanda não é contagem de pessoas únicas.
- **Unidades:** demanda, atendimento teórico, capacidade e déficit em consultas por ano sintético (`consultas/ano`).
- **Inicialização:** `D[d,0] = residents[d,0] × annual_visits_per_resident`; `C[d,0] = residents[d,0] × initial_visits_per_resident_year`, conforme defaults sintéticos da tabela.
- **Transição anual:** capacidade segue `C[d,r] = C[d,r−1] + commissioned_visits_per_year[d,r] − retired_visits_per_year[d,r]`; demanda segue `D[d,r] = residents[d,r] × annual_visits_per_resident`. Sem evento, capacidade permanece constante. Cada alteração deve declarar a rodada efetiva.
- **Fórmula:** `served[d,r] = min(D[d,r], C[d,r])`; `unmet[d,r] = max(0, D[d,r] − C[d,r])`; `unmet_pct[d,r] = 100 × unmet[d,r] / D[d,r]`. Para `D=0`, a taxa é `null/not_applicable`. Utilização: `100 × served[d,r] / C[d,r]`; se `C=0`, `null/not_applicable`. Publicar volumes junto aos percentuais.
- **Parâmetros e limites:** taxas de demanda e capacidade em consultas por residente/ano e consultas/ano, ambas não negativas; baixa não pode exceder estoque anterior mais adição; capacidade não negativa. Qualquer limite ou mínimo de serviço é uma regra configurada/versionada, nunca um padrão presumido.
- **Desagregação:** por distrito urbano e total urbano (razões recalculadas de somas). Entorno rural, serviço por instalação, grupos e acesso em tempo/distância indisponíveis até declarar localização, captação, roteamento e dados populacionais correspondentes.
- **Incerteza e interpretação:** as taxas per capita e capacidade disponível são hipóteses; sazonalidade, equipe, indisponibilidade, encaminhamentos e fila não são representados. Resultado é balanço sintético de capacidade e demanda, não atendimento real ou cobertura espacial.
- **Proveniência:** como SER-02a, com unidades e parâmetros próprios. Não confundir consultas com pacientes únicos ou vagas escolares.

Para ambos os serviços, é permitido substituir defaults por dados observados em uma extensão futura somente com proveniência, período, cobertura e licença documentados. A mistura de insumos observados e sintéticos precisa permanecer explícita no resultado.

## 4. Indicadores ambientais com entradas explícitas

### AMB-03a — Área verde pública elegível por residente urbano

- **Entradas:** `public_green_area_m2[d]`, explicitamente declarada para cada distrito e classificada como `synthetic_config` no benchmark; residentes urbanos do snapshot ou transição demográfica. Não é calculada a partir de `land_use`.
- **Unidade:** m² de área verde pública elegível por residente (`m²/residente`), acompanhado por área total (`m²`) e residentes (`pessoas`).
- **Inicialização demonstrativa:** `A[d,0] = residents[d,0] × public_area_m2_per_resident[d]`, usando os parâmetros sintéticos da tabela. Essa operação constrói um fixture de benchmark; não alega que exista polígono, parque ou inventário cartográfico correspondente.
- **Transição anual:** `A[d,r] = A[d,r−1] + commissioned_area_m2[d,r] − removed_area_m2[d,r]`. Sem evento explícito de criação/remoção, a área permanece constante. `green_per_resident[d,r] = A[d,r] / residents[d,r]`; se população for zero/desconhecida ou a completude do inventário não for conhecida, emitir `null` com motivo.
- **Parâmetros e limites:** área e alterações em m² não negativas; remoção não pode superar estoque; elegibilidade pública deve ser uma regra de configuração (quais categorias entram), versionada. Área acima da área territorial de referência deve falhar na validação quando existir geometria/cobertura completa. Enquanto só existir área sintética agregada, não alegar tal validação espacial.
- **Desagregação:** distrito urbano e total urbano, somando áreas e populações antes da divisão. O entorno rural é excluído. Não dividir por população municipal incluindo zonas que não entram no inventário.
- **Incerteza e interpretação:** os defaults, elegibilidade, limites territoriais e população são hipóteses; a razão esconde a distribuição interna. Não mede proximidade, entrada/acesso, segurança, qualidade ecológica, sombra, biodiversidade ou exposição. Para distância/acesso seriam necessários polígonos, entradas e rede.
- **Proveniência:** área default `synthetic_config`; valor por residente `derived`. `observed` só com cadastro/levantamento real identificável.

### AMB-01a — Massa anual sintética estimada de CO₂e veicular

- **Entradas:** atividade `annual_vehicle_km[d,r]` declarada explicitamente em veículo-km/ano sintético e fator `co2e_kg_per_vehicle_km` em kg CO₂e/veículo-km. O default configura atividade como `residents[d,r] × annual_vehicle_km_per_resident` e usa os parâmetros sintéticos da tabela. Essa atividade é uma hipótese exógena independente; não é derivada das janelas AM/fora de pico do SUMO.
- **Unidade:** kg ou t de CO₂e por distrito/ano sintético. Publicar a espécie/agregado e fator usado; não somar CO₂e com NOx ou material particulado.
- **Inicialização e fórmula anual:** `VKT[d,r] = residents[d,r] × annual_vehicle_km_per_resident`; `E_kg[d,r] = VKT[d,r] × co2e_kg_per_vehicle_km`; `E_t[d,r] = E_kg[d,r]/1000`. Recalcular uma vez por rodada com atividade e fator daquela rodada. Sem entrada ou fator válido, emitir `null`, não zero.
- **Parâmetros e limites:** atividade e fator devem ser finitos e não negativos; versão, unidade, escopo do veículo e poluentes incluídos obrigatórios. O benchmark usa apenas um fator sintético ilustrativo. Limites de emissão só podem ser usados se configurados com autoridade, escopo, período e unidade; não há limite implícito.
- **Desagregação:** distrito urbano e total urbano por soma das massas; VKT pode ser publicado separadamente. Não alocar a emissão a residentes/grupos nem ao meio físico sem método adicional. O entorno rural não está incluído.
- **Incerteza e interpretação:** fator, atividade, composição da frota, combustível, velocidade e fronteira de fontes são incertos; o resultado é uma estimativa condicional aos valores configurados. A hipótese de veículo-km por residente não é observação nem previsão. Não anualizar resultados de janelas SUMO, não interpretar massa como concentração/exposição e não sugerir emissões de todas as fontes da cidade.
- **Proveniência:** atividade e fator são `synthetic_config`; produto é `estimated` (com transformação determinística `derived`) e deve guardar entradas/versões. Só um inventário independente documentado pode ser marcado `observed`.

## 5. Domínios indisponíveis nesta fatia

- **SER-01 — acesso geográfico a serviço:** indisponível. Faltam unidades localizadas, rede/custo de viagem, horário, área de captação e população elegível espacializada. Os agregados de capacidade acima não constituem distância/tempo de acesso.
- **AMB-02 — concentração ambiente:** indisponível. Não há monitoramento observado nem modelo de dispersão, meteorologia e calibração. Emissão estimada não substitui concentração.
- **Qualidade ecológica, exposição individual e acesso verde:** indisponíveis sem dados/modelos próprios.
- **Cobertura do entorno rural:** indisponível até que a fronteira geográfica, população servida e alocação entre zonas sejam definidas.

Os quatro cálculos propostos são demonstradores sintéticos condicionados a entradas explicitamente adicionadas e versionadas. Se a integração não fornecer essas entradas, o indicador correspondente continua ausente com motivo; não preencher com os defaults silenciosamente.

## 6. Contrato de publicação e critérios testáveis

Cada valor anual publicado deve conter: `indicator_id` e versão; valor ou `null` e motivo; unidade; fórmula/método e versão; ano/rodada; distrito ou território; numerador, denominador e volumes quando aplicável; cobertura; `provenance_kind` por entrada e saída; parâmetros e fontes com versão; snapshot/estado pai e estado resultante; produtor/modelo/versão; incerteza/limitações e avisos. A população de referência, a área coberta e a exclusão do entorno rural devem acompanhar os agregados.

Critérios de aceitação para a implementação futura:

1. **Validação de entradas:** rejeitar unidades ausentes/incompatíveis, valores não finitos, negativos, shares fora de `[0,1]`, IDs de distrito duplicados e evento de baixa acima do estoque. Ausência de dado resulta em `null` com motivo.
2. **Balanço anual:** para cada distrito e serviço, `estoque_novo = estoque_anterior + entradas_efetivas − baixas_efetivas`; estoque permanece não negativo e eventos com atraso só alteram a capacidade na rodada efetiva.
3. **Atendimento:** `0 ≤ served ≤ min(demand, capacity)`; `unmet = demand − served ≥ 0`; quando `demand > 0`, `unmet_pct = 100 × unmet/demand`; quando `capacity > 0`, utilização fica em `[0,100]`. Denominador zero produz `not_applicable`, não `NaN`, infinito ou percentual zero.
4. **Agregação:** total urbano de demanda, capacidade, atendimento, déficit e área iguala a soma dos cinco distritos; percentuais são recalculados dos totais, nunca médias simples de percentuais. O entorno rural não entra sem regra explícita.
5. **Área verde:** saída muda apenas com entrada explícita de área, população ou evento de estoque. Alterar somente o texto `land_use` não pode mudar área nem indicador.
6. **Emissões:** com entradas constantes, a fórmula reproduz exatamente `VKT × fator`; conversão kg→t é por 1.000. Alterar as métricas das janelas SUMO sem alterar a entrada anual de atividade não altera o resultado. Não existe transformação para µg/m³.
7. **Proveniência:** fixture inicial e parâmetros ficam rotulados `synthetic_config`; execução anual, `simulated`; estimativa de CO₂e, `estimated`; razões/totalizações, `derived`; nenhum destes recebe `observed` por default.
8. **Reprodutibilidade e atomicidade:** mesmo estado, parâmetros, eventos e versão de regra produzem os mesmos resultados; falha de qualquer validação aborta a publicação conjunta do estado e métricas anuais.
9. **Limites:** limites de serviço ou ambientais só são restrições se configurados e versionados. Testar limiar exato, abaixo e acima, sem incorporar limites legais fictícios.

## 7. Dependências para integração

1. **Estado/configuração versionados:** adicionar modelos estritos para parâmetros dos domínios, unidades, proveniência, entradas ambientais, capacidade inicial e eventos anuais. A compatibilidade deve ser opcional/migrável; esta especificação não altera YAML compartilhado.
2. **População de entrada:** formalizar o consumo dos residentes por distrito do snapshot e o contrato com eventual modelo demográfico. Manter o snapshot inicial imutável e usar o estado comprometido anterior nas rodadas seguintes.
3. **Eventos/ações e calendário:** definir criação/baixa/atraso de capacidade e área, validação de alvos, custos e autorização. Enquanto essas regras não forem integradas, testar apenas transições sem ação ou fixtures versionadas, sem sugerir política operacional habilitada.
4. **Motor de rodada:** declarar ordem e executar os modelos uma vez por ano, sobre estado candidato; validar invariantes e publicar estado/eventos/indicadores de forma atômica, em linha com o contrato de rodadas da referência integrada.
5. **Catálogo/saída:** adicionar IDs, unidades, status de prontidão, nulos e motivos, proveniência, desagregação e incerteza ao catálogo/contrato de resultado. Preservar entradas e parâmetros que permitem reproduzir cada valor.
6. **Validação empírica futura:** substituir hipóteses por registros/licenças/fontes locais somente com cobertura temporal/espacial e responsável documentados. Escolas e unidades reais exigem localização, vagas, operação e elegibilidade; ambiente requer atividade/fatores adequados e, para concentração, monitoramento ou modelo de dispersão calibrado. Hipóteses sintéticas nunca validam por si mesmas os resultados que geraram.

## Referências do projeto

- `configs/cities/aurora-base-v1.yaml` — população, distritos, rótulos de uso do solo e relógio sintético.
- `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` — contratos previstos para estado, serviços, ambiente e escalas dos modelos.
- `docs/arquitetura/arquitetura-completa-urban-twin-arena.md` — domínios, proveniência e execução da Arena.
- `/home/gusta/.t3/worktrees/city_engine/feature-aurora-round-engine/docs/especificacao/estado-cidade-v1.md` — referência integrada de campos presentes/ausentes; consultada somente para leitura.
- `/home/gusta/.t3/worktrees/city_engine/feature-aurora-round-engine/docs/especificacao/catalogo-indicadores-v1.md` — definições SER-02, SER-03, AMB-01 e AMB-03; consultada somente para leitura.
- `/home/gusta/.t3/worktrees/city_engine/feature-aurora-round-engine/docs/especificacao/rodadas-acoes-v1.md` — relógio, estado candidato, efeitos com atraso e publicação atômica; consultada somente para leitura.

# Catálogo de indicadores urbanos — v1

**Status:** especificação de indicadores; não é protocolo de validação nem declaração de que os modelos estejam implementados.

**Escopo:** mobilidade, finanças, habitação, serviços, ambiente e equidade para experimentos da Urban Twin Arena. Aurora é uma cidade sintética de benchmark. A ficha de piloto de trânsito observado continua sendo a referência para futura validação empírica.

## 1. Como interpretar o catálogo

Cada ficha define a grandeza, o cálculo, a unidade, a direção de leitura, as dimensões de desagregação, o período, a proveniência, a incerteza, limitações e a prontidão atual. As fórmulas são contratos conceituais: quando as entradas necessárias não existirem, o indicador fica indisponível, não recebe zero nem valor imputado silenciosamente.

### Status de prontidão

- **Computável hoje:** a implementação atual calcula e expõe a métrica, ou todos os seus insumos já são expostos e permitem derivação determinística sem modelo ou fonte novos. Cada ficha distingue métrica direta de métrica derivada não exposta como campo próprio. É computável sobre uma execução sintética/simulada, não evidência de trânsito observado.
- **Requer modelo:** o catálogo define uma métrica de saída, mas falta implementar o modelo de domínio ou o cálculo integrado necessário. Parâmetros sintéticos, por si só, não tornam uma transição urbana executável.
- **Requer dado observado:** a grandeza descrita é empírica e não pode ser preenchida para um território/período real sem observações adequadas e autorizadas. Um modelo poderá produzir uma estimativa separada, sem convertê-la em observação.

O status descreve a prontidão deste projeto, não a importância ou validade universal do indicador. As seis métricas brutas de mobilidade são calculadas e expostas pelo contrato atual; a taxa de conclusão listada abaixo é uma derivação possível dessas métricas, não um campo próprio da API. Outros valores atualmente presentes apenas como entrada/configuração não equivalem a resultados de um modelo.

### Proveniência e rótulos de resultado

Preservar o tipo de cada entrada e saída em armazenamento, API e relatório:

O contrato integrado v1 registra origem e método em campos independentes, evitando misturar categorias diferentes:

| Campo | Valores v1 | Significado |
|---|---|---|
| `source_kind` | `synthetic_config`, `synthetic_generated`, `external_dataset`, `observed` | Origem dos dados e parâmetros usados. `observed` exige fonte, licença, cobertura e período auditáveis. |
| `production_method` | `measured`, `derived`, `simulated`, `estimated` | Como o valor foi produzido. Um resultado derivado ou simulado mantém a origem de suas entradas. |

Os rótulos legados usados nas fichas continuam significando: `synthetic_config`/`synthetic_generated` são origens; `observed` é origem empírica; `derived`, `simulated`, `estimated` são métodos. A API e o armazenamento devem normalizá-los para os dois campos do contrato; não criar um `provenance_kind` misto.

Um indicador pode combinar tipos. Registrar a proveniência no nível das entradas e do resultado; não trocar o rótulo para “observado” só porque uma saída simulada se parece com uma grandeza mensurável. Uma comparação observado–simulado guarda ambos os lados e o método de comparação separadamente.

### Direção e agregação

“Maior” e “menor” indicam orientação usual, não um objetivo universal. A direção pode depender de contexto, grupo, horizonte e limiar definido pelo experimento. Indicadores com direção **contextual** não devem ser otimizados sem explicitar o perfil de avaliação. Não combinar unidades distintas em score sem escolha explícita de normalização e pesos, definida antes da execução e acompanhada por sensibilidade. O padrão é exibir o vetor, distribuições/intervalos, desagregações e trade-offs.

## 2. Restrições obrigatórias e objetivos

Restrições são gates verificáveis e não compensáveis: uma melhora em outro indicador não apaga sua violação. Objetivos são dimensões de comparação que podem conflitar. Não há limites numéricos universais neste catálogo: limites legais, de segurança, fiscais ou de serviço devem ser fornecidos pela autoridade competente e fixados no escopo territorial e temporal do experimento.

### Restrições obrigatórias do cálculo e do experimento

1. **Integridade:** `viagens solicitadas = concluídas + não concluídas`; contagens não negativas; denominadores, unidades, território, janela e população elegível identificados. Denominador zero ou desconhecido produz `null`/“não calculável” e motivo, nunca zero por conveniência.
2. **Comparabilidade:** comparações pareadas usam snapshot, demanda expandida, janela, período de escoamento, semente e regras comuns, exceto a intervenção declarada. Uma falha de execução invalida a comparação e não publica deltas parciais.
3. **Dados e proveniência:** fonte, versão, licença/base de uso quando pertinente, transformação, cobertura espacial/temporal e classificação da proveniência são obrigatórias. Ausência de cobertura significa desconhecido, não inexistência confirmada.
4. **Validade de restrições configuradas:** orçamento, capacidade, área protegida, padrões legais ou níveis mínimos só são gates quando regra, autoridade, unidade, população abrangida e período tiverem sido explicitamente configurados e versionados. Não inferir limiar deste catálogo.
5. **Privacidade e equidade:** desagregar somente com base legal, finalidade e granularidade compatíveis. Proteger grupos pequenos; supressão por privacidade deve ser identificada e não pode virar zero ou cobertura completa.
6. **Uso empírico:** alegações sobre cidade real requerem observações independentes adequadas à pergunta e ao período. A saída do mesmo modelo usado para produzir o resultado não é validação independente.

### Objetivos catalogados

Tempo e conclusão de viagens, filas, equilíbrio fiscal, adequação habitacional, acesso e cobertura de serviços, emissões/exposição ambiental e redução de disparidades são **objetivos** ou dimensões de diagnóstico, não restrições automáticas. Um experimento pode adotar limiar para algum deles, mas deve documentar fonte e autoridade do limiar, período, grupos afetados e efeito de dados ausentes. Não maximizar uma métrica isolada sem revisar efeitos em bairros e grupos.

## 3. Mobilidade

As métricas abaixo são saídas da simulação da demanda sintética expandida pelo adaptador SUMO. Não representam contagens, tempos ou velocidades observados em Aurora ou em cidade real. Na execução atual, as médias de duração e velocidade cobrem viagens concluídas até o fim do escoamento; a fila cobre apenas a janela de demanda. Não anualizar janelas representativas.

### MOB-01 — Viagens solicitadas

- **Definição:** quantidade de veículos/viagens gerados pela expansão da demanda OD sintética para a janela executada.
- **Fórmula:** `N_solicitadas = Σ_od round(taxa_veículos_od_por_hora × duração_da_janela_s / 3600)`; o adaptador distribui as partidas de cada OD uniformemente na janela. Não interpretar como pessoas.
- **Unidade:** veículos/viagens por execução e janela.
- **Direção:** não é objetivo; é denominador/volume de entrada para interpretar atendimento.
- **Território/grupo:** rede/OD da execução; por origem, destino ou modo somente se as chaves forem preservadas.
- **Período:** janela de demanda configurada.
- **Fonte/proveniência:** taxas OD sintéticas (`synthetic_config`/`synthetic_generated`) e regra de expansão do adaptador; contagem derivada (`derived`).
- **Incerteza:** a expansão atual é determinística para taxas e janela fixas; a semente não altera a contagem solicitada. O arredondamento por OD pode alterar o total fracionário teórico. Incerteza estrutural da demanda não é estimada por essa contagem.
- **Limitação:** conta veículos expandidos, não necessariamente pessoas, viagens totais do município ou demanda observada.
- **Status:** **computável hoje**.

### MOB-02 — Viagens concluídas

- **Definição:** quantidade de viagens solicitadas com registro de chegada até o fim do escoamento.
- **Fórmula:** `N_concluídas = número de registros de chegada válidos`; validar que `0 ≤ concluídas ≤ solicitadas`.
- **Unidade:** veículos/viagens por execução e janela.
- **Direção:** maior é desejável somente quando demanda e condições pareadas são comparáveis; interpretar com tempo e cobertura.
- **Território/grupo:** rede total; por OD ou grupo apenas se resultado mantiver essas chaves.
- **Período:** partidas na janela de demanda e chegada até `drain_limit_seconds` após o início da execução.
- **Fonte/proveniência:** registros de chegada do SUMO (`simulated`), contados em relação à demanda sintética expandida.
- **Incerteza:** semente/replicações e variação do modelo; uma execução não representa variabilidade empírica.
- **Limitação:** mede veículo simulado concluído, não pessoa atendida nem causa de eventual não conclusão.
- **Status:** **computável hoje**.

### MOB-03 — Viagens não concluídas

- **Definição:** viagens solicitadas sem registro de chegada ao fim do período de escoamento.
- **Fórmula:** `N_não_concluídas = N_solicitadas − N_concluídas`; deve reconciliar exatamente com as contagens publicadas.
- **Unidade:** veículos/viagens por execução e janela.
- **Direção:** menor costuma ser preferível, junto da demanda de entrada e do limite de escoamento.
- **Território/grupo:** rede total; desagregação depende de saída que preserve OD/grupo.
- **Período:** mesmo período de MOB-02, até o limite de escoamento informado.
- **Fonte/proveniência:** diferença derivada (`derived`) entre demanda sintética e chegadas simuladas pelo SUMO (`simulated`).
- **Incerteza:** sensível à janela, regra de escoamento, demanda expandida e semente.
- **Limitação:** não distingue viagem ainda em curso, falha de rota, teleportação ou outra causa sem diagnóstico complementar.
- **Status:** **computável hoje**.

### MOB-04 — Taxa de conclusão de viagens

- **Definição:** fração de viagens/veículos solicitados cuja chegada foi registrada até o limite de escoamento.
- **Fórmula:** `100 × N_concluídas / N_solicitadas`; não calculável se solicitadas = 0.
- **Unidade:** `%`.
- **Direção:** maior costuma ser preferível; interpretar junto de duração e escoamento.
- **Território/grupo:** rede modelada total; por zona/distrito ou classe de viajante somente se a entrada/resultados preservarem essa chave.
- **Período:** partidas na janela de demanda; chegada contada até `drain_limit_seconds` após o início da execução. Informar janela e limite.
- **Fonte/proveniência:** contagens MOB-01/MOB-02 (`synthetic_generated`/`simulated`), razão derivada (`derived`).
- **Incerteza:** variação entre sementes/replicações; erro de demanda e estrutura do modelo não é capturado por uma única execução.
- **Limitação:** taxa não identifica, por si só, causa de não conclusão ou experiência do viajante; depende do limite de escoamento.
- **Status:** **computável hoje** (derivável das contagens atuais; não exposta como campo próprio na API).

### MOB-05 — Duração média das viagens concluídas

- **Definição:** média aritmética de duração porta-a-porta simulada para viagens com chegada registrada.
- **Fórmula:** `Σ duração_i / N_concluídas`; `null` se não houver conclusão. Não calcular média sobre viagens incompletas.
- **Unidade:** segundos por viagem (`s/viagem`).
- **Direção:** menor costuma ser preferível, condicionado a segurança, acesso e distribuição dos efeitos.
- **Território/grupo:** rede/cidade sintética total; desagregar por OD, distrito ou grupo somente se vínculo individual sintético for preservado e documentado.
- **Período:** partidas dentro da janela; inclui duração até chegada dentro do período de escoamento. Não é média diária ou anual.
- **Fonte/proveniência:** `tripinfo` do SUMO (`simulated`), produzido a partir de rede e demanda sintéticas; duração calculada (`derived`).
- **Incerteza:** sementes e replicações; apenas viagens concluídas entram na média. Ler junto com MOB-02 e MOB-03, pois viagens não concluídas não entram no denominador.
- **Limitação:** média pode esconder caudas e disparidades; tráfego, rede, demanda e parâmetros sintéticos não validam tempo real.
- **Status:** **computável hoje**.

### MOB-06 — Velocidade média ponderada pela distância

- **Definição:** distância total de rota das viagens concluídas dividida pela duração total dessas viagens.
- **Fórmula:** `3,6 × Σ distância_i(m) / Σ duração_i(s)`; `null` se nenhuma viagem for concluída ou duração total = 0. É razão de totais, não média simples das velocidades individuais.
- **Unidade:** km/h.
- **Direção:** contextual; velocidade maior não é necessariamente melhor, especialmente para segurança viária, caminhabilidade ou acesso.
- **Território/grupo:** rede sintética total; a saída agregada atual não garante detalhe por via, modo ou grupo.
- **Período:** viagens concluídas até o fim do escoamento, cujas partidas ocorreram na janela definida.
- **Fonte/proveniência:** distância e duração no `tripinfo` SUMO (`simulated`), cálculo derivado (`derived`).
- **Incerteza:** variação de replicações, além da sensibilidade à demanda e aos parâmetros de rede.
- **Limitação:** velocidade média de viagens concluídas sofre viés de seleção e não informa limite legal, risco, congestionamento localizado ou velocidade observada.
- **Status:** **computável hoje**.

### MOB-07 — Comprimento médio de fila

- **Definição:** média aritmética simples, na janela de demanda, da soma do comprimento de fila reportado nas faixas para cada amostra gravada.
- **Fórmula:** `Σ_t(Σ_f comprimento_fila_{f,t}) / N_amostras`; cada amostra gravada tem o mesmo peso, sem ponderação pela duração do intervalo. Exibir `null` se não houver amostra válida.
- **Unidade:** metros de comprimento de fila agregados na rede (`m`); não é número de veículos.
- **Direção:** menor costuma ser preferível, junto com taxa de conclusão e demanda servida.
- **Território/grupo:** rede completa; espacializar por aresta apenas quando a série por faixa/aresta estiver preservada.
- **Período:** somente a janela de demanda, não inclui escoamento posterior.
- **Fonte/proveniência:** saída de fila do SUMO (`simulated`); parâmetro de fila e discretização do modelo devem acompanhar o valor.
- **Incerteza:** replicações e dependência do limiar de velocidade usado pelo SUMO para caracterizar veículo enfileirado.
- **Limitação:** soma espacial não mede diretamente demora, extensão de fila por corredor ou pessoas afetadas; valor agregado pode mascarar concentração local.
- **Status:** **computável hoje**.

## 4. Finanças públicas

O orçamento de Aurora usa créditos simulados (CS), sem conversão para moeda. Ainda não há modelo financeiro implementado segundo os documentos de referência; as fichas definem saídas pretendidas, não valores atuais.

### FIN-01 — Saldo operacional do período

- **Definição:** receitas reconhecidas menos despesas operacionais reconhecidas no período contábil do experimento.
- **Fórmula:** `receitas_operacionais − despesas_operacionais`; publicar componentes e regra de reconhecimento. Separar investimento de capital de operação.
- **Unidade:** CS por rodada/ano sintético para Aurora; moeda e período contábil declarados para dado observado.
- **Direção:** contextual; saldo positivo isolado não garante manutenção ou serviço adequado.
- **Território/grupo:** governo municipal/modelado; alocação por programa ou distrito somente com contabilidade rastreável.
- **Período:** rodada fiscal declarada; não misturar escala anual com janela de mobilidade.
- **Fonte/proveniência:** futuro razão/modelo financeiro (`simulated`) e parâmetros de Aurora (`synthetic_config`); para cidade real, registros orçamentários licenciados (`observed`).
- **Incerteza:** regras fiscais simplificadas, arrecadação projetada, custos e defasagens; intervalo entre cenários/replicações quando estocástico.
- **Limitação:** não equivale a resultado fiscal de município real; depende de classificação de despesas, transferências, inflação e regime contábil.
- **Status:** **requer modelo**.

### FIN-02 — Cobertura do serviço da dívida

- **Definição:** capacidade das receitas recorrentes elegíveis de cobrir pagamentos de principal e juros no período.
- **Fórmula:** `receitas_recorrentes_elegíveis / serviço_da_dívida`; se serviço da dívida = 0, registrar `not_applicable` (ou razão não definida), nunca infinito.
- **Unidade:** razão (`x`) ou percentual (`100 × razão`), sem misturar representações.
- **Direção:** maior cobertura costuma indicar maior folga, respeitados critérios fiscais aplicáveis.
- **Território/grupo:** município; não atribuir a domicílios sem outro indicador e fonte.
- **Período:** período fiscal compatível entre receitas e serviço da dívida.
- **Fonte/proveniência:** modelo/razão financeiro futuro (`simulated`); dívida e execução orçamentária municipal para avaliação empírica (`observed`).
- **Incerteza:** projeção de receitas, calendário de amortização, taxa e condições de crédito; informar cobertura de cada entrada.
- **Limitação:** denominadores e conceitos fiscais variam entre jurisdições; não se estabelece aqui um nível “seguro”.
- **Status:** **requer modelo**.

### FIN-03 — Passivo de manutenção pendente

- **Definição:** custo estimado das necessidades de manutenção vencidas e ainda não atendidas no inventário de ativos considerado.
- **Fórmula:** `Σ custo_de_reparo_j` para ativos elegíveis com intervenção pendente; reportar também cobertura do inventário (`ativos avaliados / ativos elegíveis`).
- **Unidade:** CS (Aurora) ou moeda local e data-base; opcionalmente percentual do custo de reposição, se esse denominador existir.
- **Direção:** menor passivo tende a ser preferível, considerando qualidade e completude do inventário.
- **Território/grupo:** ativo, classe de infraestrutura e distrito; somatório municipal apenas com cobertura informada.
- **Período:** posição na data de referência/fecho de rodada; custos atualizados com data-base explícita.
- **Fonte/proveniência:** inventário, condição e custos do futuro modelo (`synthetic_config`/`simulated`); inspeção e ordens de serviço reais (`observed`).
- **Incerteza:** inspeções faltantes, condição latente, unidade de custo e vida útil; propagar faixas em vez de esconder imputação.
- **Limitação:** inventário incompleto tende a subestimar passivo; o total monetário não exprime sozinho risco ou qualidade do serviço.
- **Status:** **requer modelo**.

## 5. Habitação

Não há modelo ativo de estoque, preço, ocupação ou deslocamento. Parâmetros sintéticos de domicílios de Aurora não autorizam inferir preço, disponibilidade ou efeito distributivo observado.

### HAB-01 — Ônus habitacional dos domicílios

- **Definição:** proporção da renda domiciliar destinada ao custo habitacional, sob definição de custo e renda especificada.
- **Fórmula:** por domicílio `100 × (aluguel + custos habitacionais elegíveis) / renda disponível`; relatório agregado deve declarar estatística (mediana, distribuição e numerador/denominador), não apenas média. Renda zero ou faltante não entra silenciosamente no denominador.
- **Unidade:** `% da renda domiciliar`.
- **Direção:** menor ônus pode ser desejável, mas deve ser lido com adequação, qualidade e localização da moradia.
- **Território/grupo:** domicílio/zona/distrito e grupos de renda ou composição; proteção de células pequenas.
- **Período:** mesmo mês ou ano de referência para renda e custo; distinguir valor corrente de real e informar data-base.
- **Fonte/proveniência:** pesquisa/registro de renda e custo habitacional para valor real (`observed`); saída de preço/renda de modelo futuro apenas como `simulated`.
- **Incerteza:** subdeclaração de renda/aluguel, cobertura da pesquisa, informalidade e imputação; reportar não resposta.
- **Limitação:** razão não capta qualidade, tamanho, segurança da posse, composição domiciliar nem diferenças de custo de vida.
- **Status:** **requer dado observado**.

### HAB-02 — Domicílios em moradia inadequada

- **Definição:** fração dos domicílios que satisfaz pelo menos um critério de inadequação previamente definido para o estudo.
- **Fórmula:** `100 × domicílios que atendem ≥1 critério / domicílios elegíveis avaliados`; publicar critérios, componentes, cobertura e casos indeterminados. Não presumir que todo critério de déficit habitacional seja intercambiável.
- **Unidade:** `% de domicílios`; componentes também em domicílios.
- **Direção:** menor costuma ser desejável conforme definição e período de referência adotados.
- **Território/grupo:** zona/distrito e grupos domiciliares relevantes, sujeito à privacidade.
- **Período:** data/período da pesquisa domiciliar e janela de validade dos critérios.
- **Fonte/proveniência:** censo, cadastro ou levantamento habitacional com metodologia e licença (`observed`); cenário sintético/modelo só recebe `simulated`.
- **Incerteza:** subcobertura de assentamentos, não resposta, qualidade da classificação e diferenças metodológicas entre fontes.
- **Limitação:** critérios normativos e fontes variam; um registro administrativo não representa automaticamente todos os domicílios.
- **Status:** **requer dado observado**.

### HAB-03 — Domicílios deslocados involuntariamente

- **Definição:** domicílios forçados a deixar a unidade/zona por intervenção, remoção, desastre ou pressão de custo, conforme definição do experimento.
- **Fórmula:** `100 × domicílios deslocados involuntariamente / domicílios expostos e elegíveis`; contar eventos e domicílios únicos separadamente. Se não houver coorte/registro de exposição, não calcular taxa.
- **Unidade:** domicílios e `% da coorte elegível`.
- **Direção:** menor é desejável; política de relocação voluntária e desfecho pós-mudança exigem leitura própria.
- **Território/grupo:** área de intervenção e domicílios por renda, tenure e grupo protegido quando legal e estatisticamente seguro.
- **Período:** antes/depois da intervenção, com janela de acompanhamento publicada.
- **Fonte/proveniência:** acompanhamento de domicílios, registro fundiário/administrativo ou pesquisa com método de ligação (`observed`); um modelo futuro não substitui esse acompanhamento.
- **Incerteza:** mobilidade não rastreada, definição de voluntariedade, mudança de endereço e perda de acompanhamento.
- **Limitação:** associação temporal não prova causalidade; risco de exposição e janela de observação alteram o denominador.
- **Status:** **requer dado observado**.

## 6. Serviços urbanos

Cobertura geográfica é proxy de acesso, não prova de qualidade, disponibilidade de vaga ou uso. O catálogo separa população elegível, capacidade, distância/tempo e não atendimento; nenhum limite de atendimento é fixado aqui.

### SER-01 — População sem acesso dentro do critério configurado

- **Definição:** proporção da população elegível cuja viagem a um serviço essencial excede o limite de acesso definido pelo experimento.
- **Fórmula:** `100 × elegíveis com menor custo generalizado até serviço > τ / elegíveis com origem conhecida`; `τ`, modo, horário e custo generalizado precisam ser declarados. Se a rede/locais forem incompletos, resultado é desconhecido ou cobertura parcial.
- **Unidade:** `% da população elegível` e contagem correspondente.
- **Direção:** menor é geralmente desejável, sem substituir qualidade ou capacidade.
- **Território/grupo:** origem residencial/zona, distrito, tipo de serviço e grupo; incluir serviço mais próximo usado no cálculo.
- **Período:** ano/rodada populacional e período operacional do serviço; horário de viagem compatível com o objetivo.
- **Fonte/proveniência:** rede e demanda sintéticas + modelo de rede/serviço (`simulated`); endereços, serviços e população georreferenciados de fonte apropriada (`observed`) para cidade real.
- **Incerteza:** localização geocodificada, barreiras, horários, rotas disponíveis, modo e limiar `τ`.
- **Limitação:** distância/tempo potencial não mede qualidade, lotação, elegibilidade real ou decisão individual de usar o serviço.
- **Status:** **requer modelo**.

### SER-02 — Demanda de serviço não atendida

No contrato integrado v1, escola e atenção primária são subindicadores tipados `SER-02a` e `SER-02b`, ambos com `base_indicator_id=SER-02` e versões/unidades próprias. Seus volumes não são somados entre unidades diferentes.

- **Definição:** demanda elegível que excede capacidade efetivamente disponível no período.
- **Fórmula:** `100 × max(0, demanda − capacidade_utilizável) / demanda`; reportar volumes e método de alocação; se demanda = 0, não aplicável.
- **Unidade:** `% da demanda` e unidades próprias do serviço (ex.: atendimentos, vagas ou m³/dia), identificadas por serviço.
- **Direção:** menor é desejável desde que a definição de demanda e qualidade seja comparável.
- **Território/grupo:** unidade prestadora/área de captação, distrito e população elegível; atribuição deve evitar dupla contagem.
- **Período:** intervalo de operação correspondente à capacidade e demanda; para serviço anual, rodada fiscal/populacional declarada.
- **Fonte/proveniência:** modelo futuro de demanda/capacidade (`simulated`) ou registros operacionais e listas de espera (`observed`).
- **Incerteza:** demanda latente, capacidade indisponível, equipe, sazonalidade e regra de alocação.
- **Limitação:** capacidade nominal não equivale a serviço prestado; lista de espera observada pode excluir quem desistiu ou não conseguiu solicitar.
- **Status:** **requer modelo**.

### SER-03 — Utilização da capacidade instalada

- **Definição:** parcela da capacidade operacional utilizada em cada unidade de serviço.
- **Fórmula:** `100 × volume atendido / capacidade operacional disponível`; apresentar distribuição por unidade. Capacidade nula/indisponível não gera percentual.
- **Unidade:** `%`; volume em unidade específica do serviço por período.
- **Direção:** contextual; baixo uso pode indicar capacidade ociosa ou localização inadequada, alto uso pode indicar saturação.
- **Território/grupo:** unidade prestadora, distrito e tipo de serviço; grupo apenas quando registros suportarem atribuição válida.
- **Período:** mesma janela operacional para volume atendido e capacidade disponível.
- **Fonte/proveniência:** modelo de serviço (`simulated`) ou registros de produção, escala e indisponibilidade (`observed`).
- **Incerteza:** capacidade efetivamente disponível, registro de atendimento, sazonalidade e mudanças de equipe.
- **Limitação:** taxa alta não significa qualidade alta; volume pode contar atendimentos repetidos e capacidade pode ser nominal.
- **Status:** **requer modelo**.

## 7. Ambiente

Emissões de veículos produzidas pelo simulador são estimativas do modelo. Concentração ambiente é outra grandeza: depende de meteorologia, dispersão, fundo e observação/calibração. Área verde é atributo espacial, não medida automática de qualidade ecológica ou acesso.

### AMB-01 — Massa de poluente emitida no cenário

O contrato integrado v1 registra `AMB-01a` separadamente como estimativa anual sintética baseada em veículo-km exógeno. Ele não é a mesma grandeza temporal/empírica desta ficha, não agrega com ela e não pode ser comparado diretamente à saída SUMO por janela.

- **Definição:** massa de poluente especificado emitida pelas fontes incluídas na fronteira modelada durante a janela.
- **Fórmula:** `Σ emissão_{fonte, intervalo, poluente}`; declarar espécie, fontes incluídas, método e tratamento de veículos não concluídos. Não converter massa emitida em concentração.
- **Unidade:** g ou kg do poluente por janela/execução; espécie identificada (por exemplo, CO₂, NOx ou PM), sem somá-las numa unidade indiferenciada.
- **Direção:** menor costuma ser desejável para poluentes definidos, lido junto com atividade atendida, exposição e fronteira do sistema.
- **Território/grupo:** rede e aresta/zona se saída espacial existir; total municipal somente para fronteira explicitada.
- **Período:** janela de mobilidade efetivamente simulada; sem anualização sem fator de expansão documentado e validado.
- **Fonte/proveniência:** fatores e atividade do SUMO/modelo (`estimated`/`simulated`) com versões e cobertura; inventário observado separado para validação.
- **Incerteza:** fatores de emissão, frota, velocidade, carga, combustível e condições ambientais; propagar parâmetro e variação de cenários.
- **Limitação:** massa emitida não mede concentração, exposição pessoal, dano à saúde ou fontes fora da fronteira.
- **Status:** **requer modelo**.

### AMB-02 — Concentração ambiente de poluente

- **Definição:** concentração medida de uma espécie em local e intervalo determinados, conforme protocolo de amostragem.
- **Fórmula:** média temporal válida `Σ C_{local,t} × duração_t / Σ duração_t`, respeitando controle de qualidade e cobertura mínima definidos pelo protocolo da fonte; estatísticas regulatórias exigem o método próprio aplicável.
- **Unidade:** µg/m³ (ou unidade declarada pela fonte) por poluente e intervalo.
- **Direção:** menor tende a indicar menor concentração para a espécie/período, mas interpretação normativa depende de padrão aplicável.
- **Território/grupo:** estação/local, grade apenas após método de interpolação explícito; não atribuir diretamente exposição individual.
- **Período:** resolução e janela da estação; informar lacunas e percentual de cobertura.
- **Fonte/proveniência:** estação/rede de monitoramento com calibração, método e licença (`observed`). Saída dispersiva, se futuramente calculada, fica como `simulated`.
- **Incerteza:** precisão do sensor, representatividade espacial, lacunas, calibração e transformação/interpolação.
- **Limitação:** ponto de monitoramento não representa uniformemente bairro ou exposição pessoal; média esconde picos.
- **Status:** **requer dado observado**.

### AMB-03 — Área verde pública por residente

O contrato integrado v1 registra `AMB-03a` como subindicador agregado sintético com versão própria, limitado aos cinco distritos urbanos; não implica cadastro espacial observado.

- **Definição:** área de espaços verdes públicos elegíveis dividida pela população residente da área de referência.
- **Fórmula:** `Σ área verde pública elegível (m²) / residentes`; se cobertura cadastral ou população estiver incompleta, publicar como parcial/desconhecido. Critérios de elegibilidade da área ficam registrados.
- **Unidade:** m² por residente.
- **Direção:** contextual; valor alto não assegura proximidade, qualidade, segurança, biodiversidade ou acesso universal.
- **Território/grupo:** distrito/zona; acesso por grupo requer rede, entradas e impedâncias relevantes.
- **Período:** data de validade do inventário geográfico e referência populacional correspondente.
- **Fonte/proveniência:** polígonos/cadastro territorial (`observed` ou `synthetic_config`) e população (`observed`, `synthetic_config`/`synthetic_generated`).
- **Incerteza:** classificação, sobreposição/dupla contagem, acesso público, atualização geométrica e erro populacional.
- **Limitação:** área administrativa ou parque privado não equivale a espaço público utilizável; razão per capita esconde distribuição espacial.
- **Status:** **requer dado observado**.

## 8. Equidade

Indicadores de equidade comparam grupos ou territórios sem presumir que uma média municipal represente todas as pessoas. Fixar definição de grupo, população de referência, unidade de comparação e salvaguardas de privacidade antes de executar. A configuração atual de Aurora não contém estratos populacionais operacionais por grupo; estes precisam ser definidos/fornecidos antes de qualquer desagregação simulada. Não inventar grupos nem inferi-los a partir dos totais por distrito. Diferenças observadas não demonstram causalidade.

### EQU-01 — Diferença de acesso entre grupos

- **Definição:** distância entre as taxas de acesso de dois ou mais grupos, para o mesmo serviço, critério, período e território.
- **Fórmula:** diferença em pontos percentuais: `max_g(p_g) − min_g(p_g)`, onde `p_g = elegíveis do grupo g dentro de τ / elegíveis do grupo g`; publicar cada `p_g`, numerador, denominador e cobertura. Pode também publicar razões como medida separada, sem substituir diferenças.
- **Unidade:** pontos percentuais (`p.p.`) e porcentagem por grupo.
- **Direção:** diferença menor costuma indicar distribuição mais igual, mas não garante que o nível de acesso seja adequado; examinar taxas absolutas.
- **Território/grupo:** grupos relevantes definidos pelo experimento e unidade espacial; não inferir grupo a partir de proxies sem validação.
- **Período:** mesmo período e janela de serviço para grupos comparados.
- **Fonte/proveniência:** população/grupos e rede de serviço; simulada somente após modelo de acesso, ou observada com dados administrativos/pesquisa legalmente apropriados.
- **Incerteza:** tamanho amostral, cobertura diferencial, classificação de grupo, geocodificação e erro de modelo.
- **Limitação:** binarização de acesso e agregação ocultam desigualdades internas e interseccionais; resultado é sensível a τ e grupos escolhidos.
- **Status:** **requer modelo**.

### EQU-02 — Diferença de ônus habitacional entre grupos

- **Definição:** diferença entre a distribuição de custo habitacional relativo à renda para grupos socioeconômicos definidos.
- **Fórmula:** `100 × [mediana_g(custo_habitacional / renda_disponível) − mediana_ref(custo_habitacional / renda_disponível)]`, onde `ref` é o grupo de referência declarado antes da análise; publicar distribuição, sinal da diferença e tratamento de renda nula/faltante. Comparações de mediana não substituem caudas de alto ônus.
- **Unidade:** pontos percentuais de renda domiciliar.
- **Direção:** redução de diferenças pode ser desejável, desde que o ônus e a adequação de cada grupo também melhorem.
- **Território/grupo:** grupos de renda, tenure e composição domiciliar em zonas/distritos, com salvaguarda de células pequenas.
- **Período:** custos e rendas do mesmo período e base monetária; janela de acompanhamento se longitudinal.
- **Fonte/proveniência:** pesquisa/cadastro domiciliar com cobertura e proteção apropriadas (`observed`). Estimativa de modelo futuro deve ser rotulada separadamente como `simulated`.
- **Incerteza:** subdeclaração, não resposta, custo imputado, definição de grupo e amostra pequena.
- **Limitação:** razão e diferença não medem qualidade, segurança da posse, preferência locacional ou efeitos causais da política.
- **Status:** **requer dado observado** para valor empírico de cidade real. Uma execução futura com valores sintéticos/modelados será separada e rotulada `simulated`; não há modelo habitacional atual.

### EQU-03 — Lacuna de nível mínimo de serviço por grupo

- **Definição:** maior déficit entre o nível de acesso/serviço de um grupo e um mínimo explicitamente adotado pelo experimento.
- **Fórmula:** `max_g max(0, τ_min − nível_g)`; τ_min e sentido da escala precisam ser versionados. Se o experimento não declarar mínimo e unidade, indicador não é instanciado.
- **Unidade:** unidade do nível de serviço (por exemplo, p.p. de acesso); não agregar dimensões distintas.
- **Direção:** menor déficit; zero significa apenas que o mínimo configurado foi atingido pelos grupos avaliáveis.
- **Território/grupo:** cada grupo e território elegíveis, além do grupo responsável pelo máximo; respeitar privacidade.
- **Período:** período ao qual o padrão e a observação/modelo se aplicam.
- **Fonte/proveniência:** indicador de serviço por grupo mais padrão/compromisso com fonte e autoridade documentadas; componente simulado não vira prova de cumprimento real.
- **Incerteza:** incerteza do nível por grupo, cobertura e definição do mínimo; reportar intervalos em torno da margem quando possível.
- **Limitação:** não há padrão universal neste catálogo; se o mínimo for escolhido pelo próprio experimento, resultado não é certificação legal.
- **Status:** **requer modelo**.

## 9. Registro mínimo por valor publicado

Além dos campos de cada ficha, cada valor armazenado/publicado deve identificar `indicator_id` e versão, valor ou `null` com motivo, unidade, método/fórmula versionada, território, período, grupo (ou “não desagregado”), numerador/denominador quando aplicável, cobertura e filtros, proveniência, fonte/artefato e checksum quando existir, licença/base de uso, produtor e versão, snapshot/modelo/execução/semente quando simulados, intervalo ou método de incerteza, limitações/avisos e restrições configuradas aplicáveis. Mudança de fórmula, população de referência, janela ou unidade requer nova versão e preservação da definição anterior.

## 10. Limites de interpretação

- As métricas atuais de mobilidade descrevem uma execução do benchmark sintético Aurora/SUMO. Uma saída de simulação não é dado observado nem, sem avaliação independente, estimativa validada de cidade real.
- Uma observação empírica continua sendo observação, inclusive quando comparada a uma simulação; diferença, viés e cobertura são novos resultados derivados e devem apontar aos dois insumos.
- Finanças, habitação, serviços, ambiente e equidade neste catálogo são especificações. O fato de uma fórmula ser expressável não significa que os dados, modelos, balanços ou validação necessários existam.
- Resultados devem permanecer multidimensionais e desagregados quando os dados e salvaguardas permitirem. Este documento não fornece pesos, normalização comum, ranking, limiar universal ou valor de referência.

## 11. Relação com documentos do projeto

- [Conceito e definição de resultado](../conceito/urban-twin-arena.md): vetor de indicadores, proveniência, incerteza, trade-offs e referências externas.
- [Arquitetura completa](../arquitetura/arquitetura-completa-urban-twin-arena.md): contratos `MetricVector`/`ModelOutput`, escalas temporais, proveniência e publicação de resultados.
- [Blueprint da cidade sintética](../arquitetura/cidade-sintetica-urban-twin-arena.md): Aurora como benchmark, relógios dos domínios, grupos sintéticos, restrições e objetivos.
- [Ficha do piloto](../piloto/ficha-piloto.md): recorte, fontes, cobertura, calibração e validação com observações independentes.

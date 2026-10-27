# Experimento pareado multi-semente e multi-janela — Aurora v1

**Status:** contrato documental versionado; ainda não implementado pela API/UI.
**Escopo:** protocolo para comparar estratégias de mobilidade com baseline em execuções SUMO sintéticas, com janelas e sementes explícitas. Este documento não altera o contrato de evolução anual da Arena nem habilita novas ações.

## 1. Pergunta e limites

O primeiro estudo responde duas perguntas condicionais à configuração congelada de Aurora: (1) sementes SUMO distintas alteram as métricas observadas? e, se houver variação mensurável, (2) qual é a distribuição dos deltas pareados entre cada estratégia e o baseline em cada janela?

Hoje a Arena avalia com seed `42` e janela `weekday_am_peak`; `weekday_off_peak` também está configurada. Rotas e horários OD são determinísticos. A entrada fornecida ao baseline e à estratégia deve ser a mesma em cada par. Portanto, variar a seed testa somente a aleatoriedade operacional que SUMO de fato usa nesta configuração; não amostra demanda.

Resultados SUMO são `simulated` e seus deltas são `derived`. Aurora, rede, demanda e intervenções são sintéticas. Uma execução representa uma janela configurada e seu escoamento, não um ano, dia típico observado ou cidade real. Não anualizar, inferir validade real, prometer efeito causal, criar ranking universal, nem interpretar precisão de Monte Carlo como redução da incerteza estrutural do modelo.

O motor anual é dono de manifesto da Arena, rodada, estado evolutivo, ações e indicadores anuais. O SUMO é um avaliador opcional e isolado por janela. Sua saída pode ser referenciada como evidência de mobilidade da rodada; não altera o estado urbano, não produz indicador anual e não é somada a resultados de outras janelas.

## 2. Manifesto imutável e identidade

Antes de agendar qualquer execução, criar um manifesto canônico, validado e imutável. O manifesto tem `protocol_id: aurora-paired-multiseed-v1`, `protocol_version: 1`, `experiment_id`, data de criação e hash SHA-256 de sua serialização canônica. Uma alteração de qualquer entrada exige novo `experiment_id` e novo hash; não se edita um experimento iniciado.

O manifesto registra, no mínimo:

- referência ao manifesto imutável da Arena (`arena_manifest_id`, `arena_manifest_sha256`, `round_index`, `instance_id`) e, quando aplicável, IDs/hash de proposta e ação. O manifesto deste protocolo é subordinado e separado: nunca substitui ou altera o manifesto anual;
- cidade/configuração e versão, `snapshot_id` e hash do snapshot;
- lista ordenada e sem duplicatas de `window_id` selecionadas, horários, fuso se aplicável, unidade temporal e hash da configuração da janela; disponibilidade configurada não significa seleção automática;
- políticas/estratégias avaliadas, baseline identificado e hash/versionamento imutável de cada política, proposta e intervenção;
- lista explícita de seeds inteiras não negativas e escopo `sumo_operational_randomness`; registrar método de seleção/geração e, se aplicável, seed mestre. Não chamar esse campo de seed de demanda;
- identidade e hash da demanda expandida por janela, incluindo rotas, contagens, horários de partida e regras de escoamento. O manifesto distingue `demand_hash` da seed SUMO;
- `drain_limit_seconds`, método/versão de cálculo das métricas, versões do SUMO, adaptador, runtime, dependências relevantes e código executado (commit SHA/container digest);
- métricas primárias/secundárias, unidade, cobertura temporal e regra de comparação/IC;
- limites de execução e orçamento máximo (seção 8), número máximo de tentativas e política de retry;
- rótulos de proveniência e limitações científicas obrigatórias para apresentação.

Antes de serializar, normalizar coleções matematicamente não ordenadas: ordenar janelas e estratégias por ID e seeds numericamente; preservar a ordem de qualquer sequência semanticamente ordenada. A serialização canônica usa [JSON Canonicalization Scheme (RFC 8785)](https://www.rfc-editor.org/rfc/rfc8785.html), em UTF-8, sem propriedades duplicadas, NaN/Infinity ou valores fora do subconjunto I-JSON; entradas inválidas são rejeitadas. Hash é SHA-256 hexadecimal lowercase. `common_input_sha256` cobre snapshot, rede, demanda expandida daquela janela, janela, limites e configuração/método de métricas comuns. `arm_input_sha256` cobre `common_input_sha256` mais identidade e payload efetivo da política/intervenção daquele braço. Hashes de entrada comum e de braço são campos distintos; a paridade exige comum igual e braço diferente apenas onde a política declarada diverge.

Uma célula lógica é um par `(estratégia, baseline, window_id, seed)`. Seus dois registros de execução (um por braço) têm IDs estáveis derivados de `pair_id` e `arm_id`; cada tentativa recebe ordinal crescente e registro próprio. Uma comparação é identificada por `pair_id`, derivado do hash do manifesto, janela, seed, estratégia e baseline. Os hashes incluem a intervenção aplicada em cada braço; não substituem os hashes das entradas comuns.

Qualquer identidade repetida com o mesmo conteúdo é idempotente. A mesma chave com conteúdo diferente é conflito e não pode sobrescrever resultado. Reordenação cosmética do JSON deve gerar a mesma serialização canônica; mudança substantiva sempre cria identidade nova.

## 3. Matriz e unidade experimental

O plano é o produto cartesiano declarado `estratégia × janela × seed`. A unidade de relatório é uma célula `(estratégia, window_id, seed)` e, para comparação, um bloco pareado `(estratégia, baseline, window_id, seed)`. Para cada bloco são executados baseline e estratégia; são duas simulações SUMO por par, mesmo se uma implementação futura reutilizar baseline idêntico. Reuso só é permitido por identidade idêntica e precisa aparecer como referência explícita ao mesmo resultado, sem contabilizar execução duplicada.

Baseline e estratégia devem usar exatamente o mesmo snapshot, rede, demanda expandida, janela, seed, limites de escoamento, configuração de coleta e versões. A única diferença autorizada é a política/intervenção declarada. A igualdade é comprovada por hashes de entrada comparáveis, não apenas por igualdade de rótulos. Uma comparação que viole paridade é inválida e não gera delta.

Seeds diferentes formam réplicas Monte Carlo condicionais ao protocolo, desde que cada seed corresponda a entrada e execução identificadas. Rodar de novo a mesma seed com os mesmos bytes de entrada é repetição técnica para verificar determinismo/reprodutibilidade, não uma nova réplica independente. O mesmo conjunto de seeds pode ser usado nas duas janelas; nesse caso cada seed é um bloco medido em duas janelas, não duas seeds independentes. Resumos e incerteza continuam calculados separadamente por janela.

## 4. Piloto e dimensionamento

### 4.1 Piloto de sensibilidade à seed

Executar primeiro um piloto cujo plano, métricas, seeds, janelas selecionadas e orçamento sejam congelados antes de iniciar. Manter rede, snapshot, demanda, estratégia, limites, versão e método de cálculo fixos; variar somente a seed. Selecionar seeds por amostragem pseudoaleatória uniforme com PRNG/versão e seed mestre registrados, ou por conjunto aleatório externo documentado; não escolher seeds após inspecionar resultados. Para cada janela selecionada, executar baseline e cada estratégia em pares completos. Comparar também saídas repetidas com mesma seed/entrada em um subconjunto pré-declarado para detectar não determinismo técnico: essas execuções usam `technical_check_id` e `run_kind: reproducibility_check`, fora da matriz de réplicas, com seus próprios resultados e custos; não são retries nem novas réplicas.

O manifesto declara tolerância absoluta e relativa por métrica (ou comparação exata de valores serializados para saída discreta). Há “variação observada” numa janela/métrica se pelo menos um par de execuções válidas com seeds distintas diferir além da tolerância em um dos braços. Reportar também separadamente a variação dos deltas pareados. Este é um critério descritivo do conjunto testado, não um teste de hipótese. O piloto responde se foi observada variação entre as seeds e métricas pré-declaradas, sob a configuração testada. Se não houver, a conclusão permitida é “nenhuma variação observada nas seeds testadas sob esta configuração”; não conclui que a seed não afeta a saída em geral, não prova variância populacional zero, robustez geral ou validade do simulador. Nesse caso, não dimensionar uma alegação inferencial de efeito/robustez por seed para aquelas métricas/configuração; declarar a pergunta não sustentada pelo piloto e considerar estudo separado de demanda somente se essa for outra pergunta.

Se a pergunta seguinte exigir sensibilidade de demanda, criar outro experimento/protocolo com `demand_scenario_id` e hash próprios, variando explicitamente volumes/perfis/OD. Analisar deltas dentro de cada cenário de demanda. Não misturar a variância de seed com variação de demanda; um desenho cruzado seed × demanda requer nova identidade, orçamento do produto cartesiano e método que modele os dois fatores.

### 4.2 Escolha de réplicas após o piloto

Não há tamanho de amostra padrão neste contrato. O responsável declara métricas primárias, precisão alvo `h` (semi-largura máxima do IC da média do delta), nível de confiança, custo por execução e orçamento antes de dimensionar. Para cada par janela × métrica primária, `sΔ` é o desvio-padrão piloto dos deltas. Calcular seu limite superior de confiança de 80% `sΔ,U` sob aproximação normal dos deltas e encontrar iterativamente o menor `n ≥ 2` que satisfaz `t(1−α/2; n−1) × sΔ,U/√n ≤ h`; registrar método/pressuposto e cálculo. Se a normalidade não for plausível, declarar método conservador alternativo antes de coletar a amostra dimensionada. O `n` comum do plano é o máximo requerido entre janelas/métricas primárias, limitado pelo orçamento; não reduzir `n` post hoc porque uma métrica/janela terminou antes. Se dimensão ou precisão não couber no teto, registrar o limite e resultado exploratório.

Dimensionamento e critério de parada se aplicam por janela e métrica primária. Um limite sequencial de parada por precisão exige método de cobertura sequencial declarado antes da coleta. Caso contrário, calcular o IC apenas no `n` planejado. Não parar repetidamente quando um IC nominal de 95% aparentar resultado favorável. Se o teto de custo for atingido antes da precisão alvo, concluir “precisão alvo não atingida dentro do orçamento”, com dados incompletos/limite explícitos.

## 5. Resumos, dispersão e incerteza

Publicar sempre os resultados por execução e resumir separadamente por `(window_id, estratégia, métrica)`. Nunca juntar linhas de janelas em um único `n`, média ou IC. Não somar resultados entre seeds para formar uma observação artificial e não anualizar.

Para cada braço, janela e métrica, reportar número planejado/concluído, média, desvio-padrão amostral, mediana, intervalo interquartil e mínimo/máximo. Para estratégia versus baseline, calcular primeiro por seed o delta pareado `Δ = estratégia − baseline` na mesma janela; reportar a distribuição dos deltas com média, desvio-padrão, mediana, intervalo interquartil e extremos. Sinal favorável depende da métrica e deve ser documentado; não converter unidades para score composto.

Para a média do delta, o método primário de IC é IC t bilateral de Student de 95% sobre os `n` deltas pareados: `média(Δ) ± t(0,975; n−1) × sΔ/√n`. Declarar `n`, graus de liberdade, nível, estimador e hipótese de seeds independentes como blocos Monte Carlo representativos da aleatoriedade operacional do SUMO. Se a distribuição for fortemente assimétrica ou dominada por extremos, reportar adicionalmente bootstrap pareado por seed (percentil, 10.000 reamostragens com reposição, algoritmo de PRNG, implementação/versão e seed mestre registrados); é análise de sensibilidade e não substitui silenciosamente o método primário. Com menos de duas unidades pareadas válidas, não calcular dispersão amostral nem IC; com poucos seeds, marcar a estimativa como exploratória. ICs são marginais/descritivos por janela/métrica/estratégia. Qualquer conclusão confirmatória conjunta entre múltiplas métricas primárias, estratégias ou janelas deve pré-declarar família e correção (p.ex. Holm). Não comparar janelas como se independentes quando compartilham seeds; qualquer contraste de efeito entre janelas é outra estimativa pareada por seed e requer plano e ajuste de multiplicidade próprios. ICs representam incerteza Monte Carlo condicional ao manifesto, não incerteza do SUMO, da rede, parâmetros, demanda ou tráfego real.

Fixar métricas primárias antes da execução. Métricas secundárias são descritivas; controlar multiplicidade para qualquer conjunto de alegações confirmatórias, inclusive várias primárias, janelas ou estratégias. Para médias de tempo/velocidade sobre viagens concluídas, publicar junto contagens solicitadas, concluídas e não concluídas e limitar a interpretação: diferença na média pode refletir composição diferente de viagens concluídas. Não atribuir efeito apenas à duração/velocidade média. Preservar a semântica existente: filas cobrem a janela de demanda; tempo/velocidade cobrem viagens concluídas até o fim do escoamento.

## 6. Falhas, incompletude e retry

Estados do experimento: `queued`, `running`, `succeeded`, `partial`, `failed`, `cancelled`. Estados da execução: `queued`, `running`, `succeeded`, `failed`, `cancelled`. Toda execução conserva identidade, início/fim, tentativa, status, erro estável e referências de artefato. Métricas de execução falha/cancelada são `null`; não publicar resultados parciais do SUMO como métricas completas.

Transições válidas do experimento: `queued → running|cancelled`; `running → succeeded|partial|failed|cancelled`; `partial → running|failed|cancelled`; estados terminais não regridem, exceto criação explícita de novo retry que transita `failed` ou `partial` para `running` na mesma identidade. Execuções usam `queued → running|cancelled` e `running → succeeded|failed|cancelled`; processo encontrado `running` após reinício é marcado `failed` com erro recuperável `worker_lost` antes de retomada. Erro recuperável é apenas classe estável explicitamente configurada (timeout transitório, worker perdido ou indisponibilidade temporária do executor); erro de entrada/validação é permanente e não recebe retry automático.

Falha de um braço invalida seu par. Falha de célula não apaga outras células concluídas, mas o experimento só é `succeeded` quando todas as células obrigatórias estão completas. Pode-se disponibilizar `partial` para diagnóstico com faltantes enumerados e sem apresentar estatísticas finais como completas. Para fins descritivos de `partial`, incluir somente pares completos e marcar `selection: complete_pairs_only`, padrões de falhas e números faltantes; não calcular IC inferencial sem método de faltantes pré-registrado, pois falhas podem depender de seed/estratégia e tornar os pares restantes não representativos. IC/resumo definitivo exige conjunto completo previsto para a janela; qualquer política diferente precisa estar pré-registrada e exposta.

Retry mantém a mesma chave de célula/par e IDs por braço; incrementa ordinal no registro da execução daquele braço, sem repetir braço já confirmado. `max_attempts_per_execution` inclui a primeira tentativa e aplica-se separadamente a cada braço; cada par admite no máximo esse limite por braço. Conteúdo divergente sob mesma identidade resulta em `conflict`. Requisições simultâneas da mesma chave devem reivindicar atomicamente uma única execução; todas recebem o mesmo ID/estado idempotente e apenas uma pode consumir tentativa/orçamento. Retry após sucesso devolve o sucesso existente sem nova execução. Cancelamento não converte saída parcial em sucesso. Reinício marca trabalhos órfãos `running` como `worker_lost`, preserva tentativas/saídas confirmadas e permite somente retries recuperáveis dentro do teto.

## 7. Persistência, proveniência e DTO para API/UI

Persistir o manifesto original, seu hash, matriz planejada, estado de cada célula/par/tentativa, hashes e cópias imutáveis das entradas efetivamente consumidas, saída bruta necessária à auditoria, métricas normalizadas, logs/erros estáveis, referências e checksums de artefatos, versões, instante, custo observado e relatório estatístico. Registrar proveniência `synthetic_config`, `synthetic_generated`, `simulated` e `derived` conforme o artefato; nunca rotular saída Aurora como `observed`.

A API futura expõe DTOs tipados com `dto_schema_version` independente de `protocol_version`, sem cálculo estatístico no navegador e sem campos de domínio anual confundidos com SUMO. Deve referenciar `arena_manifest_id`/hash sem substituir o manifesto anual. Cada valor de métrica expõe `provenance_kind`, método/versão de cálculo e referência/checksum do artefato de origem; `simulated` identifica saída SUMO e `derived` identifica delta/resumo calculado. O período é definido por métrica (`demand_window` para filas; `completed_trips_through_drain` para tempo/velocidade e conclusões), não por uma janela genérica.

`planned_pairs` é a cardinalidade exata de estratégias não baseline × janelas × seeds. `completed_pairs` conta pares com dois braços bem-sucedidos; `failed_pairs` conta pares terminais inválidos; `running_pairs` inclui par com algum braço em execução; `missing_pairs` são planejados sem par final ou em execução. Deve valer `planned_pairs = completed_pairs + failed_pairs + running_pairs + missing_pairs`. Por braço, `planned_executions = planned_pairs × 2` e cada execução tem status próprio; tentativas não aumentam a cardinalidade planejada e são contadas em separado. Cache/reuso conta como resultado referenciado, não como nova execução física. Estrutura mínima:

```json
{
  "experiment": {
    "experiment_id": "<id>",
    "dto_schema_version": "1.0",
    "protocol_id": "aurora-paired-multiseed-v1",
    "protocol_version": 1,
    "manifest_sha256": "<sha256>",
    "arena_manifest_id": "<id>",
    "arena_manifest_sha256": "<sha256>",
    "status": "running",
    "planned_pairs": 0,
    "completed_pairs": 0,
    "failed_pairs": 0,
    "running_pairs": 0,
    "missing_pairs": 0,
    "limitations": ["synthetic_aurora", "window_only", "network_aggregated", "not_causal", "not_real_world_validated"],
    "pairs": [
      {
        "pair_id": "<id>",
        "strategy_id": "<id>",
        "baseline_execution_id": "<id>",
        "strategy_execution_id": "<id>",
        "window_id": "weekday_am_peak",
        "seed": 42,
        "common_input_sha256": "<sha256>",
        "status": "succeeded",
        "baseline_metrics": {"<metric_id>": {"value": 0, "unit": "<unit>", "period": "completed_trips_through_drain", "provenance_kind": "simulated", "method_version": "<version>", "artifact_sha256": "<sha256>"}},
        "strategy_metrics": {"<metric_id>": {"value": 0, "unit": "<unit>", "period": "completed_trips_through_drain", "provenance_kind": "simulated", "method_version": "<version>", "artifact_sha256": "<sha256>"}},
        "deltas": {"<metric_id>": {"value": 0, "unit": "<unit>", "direction": "strategy_minus_baseline", "provenance_kind": "derived", "method_version": "<version>"}},
        "route_exposure": "unknown",
        "executions": {
          "baseline": {"execution_id": "<id>", "status": "succeeded", "attempts": [{"attempt": 1, "status": "succeeded", "error": null, "artifact_sha256": "<sha256>"}]},
          "strategy": {"execution_id": "<id>", "status": "succeeded", "attempts": [{"attempt": 1, "status": "succeeded", "error": null, "artifact_sha256": "<sha256>"}]}
        }
      }
    ],
    "summaries_by_window": [
      {
        "window_id": "weekday_am_peak",
        "strategy_id": "<id>",
        "metric_id": "<id>",
        "unit": "<unit>",
        "period": "demand_window",
        "provenance_kind": "derived",
        "method_version": "<version>",
        "n_planned": 0,
        "n_complete": 0,
        "arm_summary": {"mean": null, "sd": null, "median": null, "iqr": null, "min": null, "max": null},
        "paired_delta_summary": {"mean": null, "sd": null, "median": null, "iqr": null, "min": null, "max": null},
        "confidence_interval": {"method": "student_t_paired", "level": 0.95, "lower": null, "upper": null, "n": 0, "degrees_of_freedom": null, "interpretation": "conditional_monte_carlo_only", "multiplicity": "marginal_descriptive"}
      }
    ]
  }
}
```

O exemplo ilustra nomes e nulabilidade, não valores permitidos ou formato final de endpoints. Cada execução e tentativa também referencia seed, janela, hashes de entrada, versão SUMO, tempo/custo e artefatos. `route_exposure` é um sinal descritivo de que alguma rota completa cruza nó alterado; `exposed` não identifica veículos afetados nem estima efeito neles. Mesmo quando `exposed`, métricas e deltas seguem agregados na rede. Ausência/inconsistência do artefato de rotas deve ser `unknown`, nunca `not_exposed` por inferência. A futura UI deve permitir ver seleção explícita de janelas, distinguir resultado incompleto de zero e exibir pares/execuções faltantes, status, provenance e limitações sem apresentar resumos parciais como completos.

## 8. Custo máximo e parada operacional

Todo manifesto contém limites finitos pré-execução: `max_sumo_runs`, `max_attempts_per_execution` (inclui tentativa inicial), `max_reproducibility_checks`, `max_wall_clock_seconds_per_run`, `max_total_wall_clock_seconds` e, quando suportado pelo executor, limites de CPU, memória e armazenamento. Antes de reuso, o teto superior de chamadas SUMO é `(n_pairs × 2 braços × max_attempts_per_execution) + max_reproducibility_checks`; também deve caber em `max_sumo_runs`. Tentativas que falhem antes de iniciar processo SUMO consomem ordinal/teto de tentativas, não chamada SUMO; qualquer processo iniciado, mesmo falhando cedo, consome uma chamada. Reuso idêntico reduz chamadas físicas somente se comprovado por identidade e referenciado como resultado cacheado; não aumenta execução planejada. `max_total_wall_clock_seconds` limita a soma do tempo de parede consumido por processos SUMO; reserva atômica de tentativas/chamadas deve impedir concorrência de ultrapassar limites.

O custo-limite teórico de plano completo é `(n_pairs × 2 braços × max_attempts_per_execution) + max_reproducibility_checks` chamadas/tentativas máximas e, conservadoramente, esse valor multiplicado por `max_wall_clock_seconds_per_run` de tempo de parede acumulado. Para aceitar uma execução que promete completar a matriz e verificações técnicas, esses limites devem caber em `max_sumo_runs` e `max_total_wall_clock_seconds`. Um piloto que intencionalmente admite incompletude pode declarar orçamento menor e critério/cobertura de parada explícitos; sua saída termina `partial` com motivo `budget_exhausted`, nunca como matriz completa. O executor não inicia sem estimativa. Durante a execução, reserva atomicamente capacidade antes de agendar, interrompe novo agendamento/retry quando excederia qualquer limite e libera reserva não consumida se o processo SUMO não iniciou. Uma execução em andamento para ao atingir seu timeout/limite; registra resultado como falha ou cancelamento, nunca como sucesso. Reportar custo planejado versus realizado por janela, seed, braço, verificação e tentativa. Infraestrutura define valores efetivos do teto antes de criar o manifesto; este contrato não inventa custo monetário nem tamanho amostral universal.

Stop criteria científicos/operacionais: (a) parar o piloto ao atingir seu orçamento máximo ou quando o teste pré-declarado de sensibilidade à seed tiver cobertura planejada; (b) ampliar/dimensionar somente com base em variabilidade piloto e precisão alvo por janela; (c) parar a expansão ao atingir o custo máximo, timeout, falhas acima do limite pré-declarado ou precisão alvo; (d) declarar explicitamente precisão não atingida quando custo limitar `n`; (e) nenhuma parada baseada em sinal favorável de IC nominal consultado repetidamente.

## 9. Critérios de aceite e testes necessários

O protocolo/documentação e sua implementação futura só são aceitáveis quando:

1. O manifesto de protocolo imutável referencia, sem substituir, manifesto/hash anual da Arena; canonicalização RFC 8785 e hashes SHA-256 permitem reconstruir toda entrada/saída.
2. Matriz cobre a cardinalidade exata sem duplicatas; contadores reconciliam (`planned_pairs = completed_pairs + failed_pairs + running_pairs + missing_pairs`); baseline/estratégia têm paridade de entrada comprovada, e diferença não autorizada invalida o par.
3. Variação de seed e cenário de demanda são fatores separados; relatório nunca chama seeds repetidas/sem variância de evidência suficiente de robustez.
4. Resumos, dispersão e IC usam unidade por seed e permanecem segregados por janela; fórmula/método, n, níveis, pressupostos, multiplicidade e faltantes aparecem no DTO/relatório.
5. Falha, cancelamento, retry, submissão simultânea duplicada e divergência de conteúdo seguem transições/idempotência especificadas; somente uma requisição reivindica execução/orçamento; métricas parciais não são apresentadas como completas.
6. Teto de chamadas, tentativas e tempo é verificado antes e durante execução com reserva concorrente; custo estimado/realizado e motivos de parada são auditáveis.
7. Artefatos e métricas têm proveniência por valor; API/UI distingue indisponível de zero e exibe limitações sintéticas, temporais, agregadas e não causais.

Testes necessários na implementação (não executados por esta entrega documental):

- hash/canonicalização do manifesto, imutabilidade e conflito de mesma chave com payload diferente;
- geração da matriz cartesiana e asserção de cardinalidade; rejeição de janela/seed duplicada ou não configurada;
- paridade exata de hashes para baseline/intervenção e rejeição de par divergente;
- demanda expandida idêntica entre seeds no protocolo de seed, verificando que só varia seed operacional;
- métricas determinísticas por célula e resumo de cada janela isolado, incluindo fórmula do delta e IC t; casos n=0, n=1 e reprodução idêntica do bootstrap sob algoritmo/versão/seed mestre fixados;
- completude, reconciliação de contadores, faltantes, status `partial`, falhas em cada braço, transições de estado, worker órfão/restart e retomada sem duplicar resultados confirmados;
- retry concorrente/idempotência: submissões simultâneas da mesma chave recebem mesmo ID/status e criam no máximo uma tentativa; retry pós-sucesso não chama SUMO; persistência após reinício;
- orçamento concorrente, timeout, limite por braço de tentativas, tentativas pré-SUMO versus processo iniciado, custo agregado e parada no limite sem agendar trabalho excedente;
- DTO/OpenAPI: versão de schema separada, nulabilidade, reconciliação de contadores, unidades, período por métrica, proveniência, referências de tentativa, estados/erros e enum de `route_exposure`; UI nunca apresenta `unknown` como ausência de exposição nem partial como resultado completo;
- regressão dos contratos atuais de execução SUMO por janela e fronteira: nenhuma métrica de janela é anualizada ou incorporada a indicador anual.

## 10. Revisões incorporadas

- **Design (revisão arquitetural de fronteiras/DTO; papel `architect` não estava disponível no roteador delegado):** SUMO permanece evidência opcional por janela, fora do estado e indicadores anuais; manifesto separado referencia o manifesto anual; seed operacional não é seed de demanda; DTO representa pares/tentativas tipados; `route_exposure` não atribui efeito individual.
- **Test-engineer:** identidade por célula/par, idempotência e retomada, matriz de custos incluindo retries, completude antes de resumo, invariantes de reconciliação e testes de contrato.
- **Critic (validade estatística):** unidade é bloco de seed pareado por janela; dispersão de braço e dispersão de delta são quantidades distintas; IC condicional não valida mundo real; critério de sensibilidade usa tolerâncias pré-declaradas; faltantes, multiplicidade e médias condicionais à conclusão limitam alegações; ausência de variação nas seeds testadas não prova robustez; sensibilidade de demanda é outro experimento.

## 11. Referências e compatibilidade

- [Contrato de evolução urbana v1](contrato-evolucao-urbana-v1.md): separação entre domínios anuais e integração SUMO.
- [Catálogo de indicadores v1](catalogo-indicadores-v1.md): semântica temporal, unidades e proveniência das métricas SUMO.
- [Contrato integrado da Arena v1](contrato-integrado-arena-v1.md): snapshot, proveniência sintética e ausência de anualização.
- [Contrato inicial dos jobs SUMO](../execucao/prompts-mvp1-4-chats.md): métricas por execução, semântica de janela/escoamento, paridade e limitações de `route_exposure`.

Este documento é o handoff documental para o Chat API. A implementação futura deverá propor endpoints, armazenamento, schemas e migrações compatíveis com este contrato antes de ligar a UI; nenhuma API ou UI foi implementada como parte desta especificação.

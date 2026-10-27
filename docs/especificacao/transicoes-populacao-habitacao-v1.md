# Transições anuais de população, habitação e empregos — v1

**Status:** proposta de desenho para o primeiro protótipo; não implementada.
**Perfil:** `aurora-base-v1`, benchmark sintético.
**Relógio:** uma rodada = um ano sintético; horizonte padrão = 10 rodadas (`arena`).
**Proveniência:** todos os parâmetros novos desta especificação são **hipóteses sintéticas de desenho**, inclusive valores padrão e faixas de sensibilidade. Não são estimativas calibradas nem validadas por fonte real.

## 1. Escopo e compatibilidade

O YAML atual fixa 67.250 residentes, 58.783 residentes urbanos, 8.467 residentes no entorno rural, 24.104 domicílios ocupados derivados de 2,79 residentes por domicílio e 24.000 empregos distribuídos por distrito. Esses números permanecem os estoques iniciais do benchmark; não são reinterpretados como observações locais. Os dados de contexto de Censo que já aparecem no YAML continuam limitados aos usos declarados nele. A especificação não cria score, indicador composto ou calibração empírica.

O código atual valida os balanços iniciais e gera snapshot determinístico. O contrato integrado fixa `round_index = synthetic_year`, início em 1, horizonte padrão 10, estado candidato isolado, validação antes de commit e transição publicada atomicamente. A política legada `protocol_noop` não executa domínio; a proposta vazia `no_action` no contrato-alvo executa os modelos anuais de referência. Esta transição produz novo candidato; falha ou estado inválido não altera o pai. A transição não modifica diretamente mobilidade ou orçamento.

## 2. Estado mínimo e estoque inicial

Manter contagens inteiras por distrito. `entorno_rural` é zona externa de captação e não recebe construção urbana. Totais sempre incluem essa zona para população; indicadores de habitação urbana excluem-na.

| Variável inicial | Regra de inicialização | Situação/proveniência |
|---|---|---|
| Residentes por distrito e total | valores atuais em `districts[].residents`; validar soma = 67.250 | existente; benchmark sintético |
| Empregos por distrito e total | valores atuais em `districts[].jobs`; validar soma = 24.000 | existente; hipótese sintética no YAML |
| Domicílios ocupados totais de referência | valor atual `occupied_households_derived: 24.104` | existente; derivado do total |
| Domicílios ocupados urbanos `H_occ_urb` | `round_half_up(P_urb / s) = 21.069` | derivação nova, separada da referência total |
| Unidades habitacionais urbanas `H_stock` | se ausente, `ceil(H_occ_urb / (1-v))`; distribuir por distrito conforme residentes urbanos pelo método de restos maiores | nova derivação; `v` é hipótese sintética |
| População-base sem grupos etários | usar apenas total e partição urbano/entorno; não inventar idades ou fertilidade específica | dados ausentes tratados como agregados |

O campo YAML `occupied_households_derived: 24.104` usa população total de 67.250; preservá-lo como referência de domicílios ocupados totais, não como unidades e nem como valor urbano. A dinâmica v1 modela somente unidades habitacionais urbanas: `H_occ_urb = round_half_up(58.783 / 2,79) = 21.069`. Com vacância padrão sintética `v=0,05`, o estoque inicial urbano ausente é `ceil(21.069 / 0,95) = 22.178` unidades. Distribuir esse estoque nos cinco distritos urbanos conforme residentes; `entorno_rural` não recebe unidades modeladas. Essa derivação não estima moradias reais e não muda o campo existente de domicílios totais.

Se `housing.initial_units` for fornecido, esse valor é o estoque agregado urbano e substitui somente a derivação de `H_stock`; alocá-lo nos distritos pela distribuição inicial de residentes. Nunca sobrescreve população ou domicílios ocupados derivados. Campo ausente usa a regra acima e registra `initialization_method`. Campo inválido (negativo, não finito, unidade incompatível) falha a validação; não substituir por zero. Arredondamento de contagens é sempre metade para cima e rateios usam restos maiores, empate por `district.id` em ordem lexicográfica.

## 3. Parâmetros configuráveis

Todos os parâmetros nesta tabela são **hipóteses sintéticas de desenho**. Faixas são testes de sensibilidade, não intervalos de confiança. Valores padrão visam mudanças graduais em dez passos anuais e não têm validação externa.

| Parâmetro (nome proposto) | Unidade | Padrão | Sensibilidade | Uso |
|---|---:|---:|---:|---|
| `demography.birth_rate` | nascimentos / residente / ano | 0,012 | 0,008–0,018 | fluxo bruto sobre população urbana e do entorno |
| `demography.death_rate` | mortes / residente / ano | 0,008 | 0,006–0,012 | fluxo bruto sobre população urbana e do entorno |
| `demography.net_migration_rate` | saldo migratório / residente / ano | 0,002 | -0,010–0,015 | fluxo líquido agregado; pode ser negativo |
| `demography.urban_net_migration_share` | fração do saldo migratório | 0,80 | 0,50–1,00 | parcela do saldo destinada à área urbana; resto ao entorno |
| `demography.household_size` | residentes / domicílio ocupado | 2,79 | 2,3–3,3 | converte residentes em demanda de domicílios; default replica proxy configurada, sem inferência local |
| `housing.vacancy_rate_target` | fração de unidades vagas | 0,05 | 0,02–0,12 | estoque necessário para atender ocupação |
| `housing.annual_capacity_rate` | fração do estoque inicial / ano | 0,02 | 0,005–0,05 | teto de unidades novas em cada rodada |
| `housing.annual_retirement_rate` | fração do estoque no início do ano | 0,003 | 0–0,015 | unidades retiradas por obsolescência sintética |
| `housing.initial_units` | unidades | ausente | n/a | opcional; se ausente, derivação da seção 2 |
| `employment.annual_growth_rate` | empregos / emprego / ano | 0,01 | -0,03–0,04 | crescimento líquido anual sintético |
| `employment.district_allocation` | frações por distrito | proporção atual | cenários: atual ± 10 p.p. renormalizados | rateio determinístico dos novos empregos; distrito externo sempre zero |

O perfil de parâmetros deverá ficar em seção separada, por exemplo `transition_v1`, ao ser integrado. Não alterar o YAML nesta entrega. Campos desconhecidos devem ser rejeitados pelo contrato estrito; versões futuras exigem versionamento. Limites numéricos devem ser validados antes da primeira rodada.

## 4. Ordem de transição e fórmulas

Entrada: estado válido no ano `t-1`, parâmetros congelados no experimento e `round_index=t`. Calcular em precisão decimal determinística; converter a inteiros apenas nos pontos de contabilização descritos. Não usar amostragem aleatória.

### 4.1 População

Para cada zona `z` (urbana consolidada ou entorno):

```text
b_z = round_half_up(P_z × birth_rate)
d_z = round_half_up(P_z × death_rate)
M = round_half_up(P_total × net_migration_rate)
M_urb = round_half_up(M × urban_net_migration_share)
M_entorno = M - M_urb
M_urb_applied = max(M_urb, -(P_urb + b_urb - d_urb))
M_entorno_applied = max(M_entorno, -(P_entorno + b_entorno - d_entorno))
P_urb' = P_urb + b_urb - d_urb + M_urb_applied
P_entorno' = P_entorno + b_entorno - d_entorno + M_entorno_applied
M_blocked = (M_urb - M_urb_applied) + (M_entorno - M_entorno_applied)
```

`M` é saldo líquido assinado; arredondamento preserva `M_urb + M_entorno = M`. O saldo negativo aplicado é limitado apenas para impedir população negativa; `M_blocked` registra o restante não aplicado. Os fluxos de nascimento/morte são agregados por zona e rateados aos distritos urbanos proporcionalmente aos residentes pré-transição, com restos maiores. Não interpretar fluxo líquido como migração de entrada observada. O modelo agregado não permite estimar envelhecimento nem fecundidade por grupo. Para manter identidade por zona, registrar separadamente nascimentos, mortes e migração aplicada; depois do limite, `P_total' = P_total + births - deaths + M_urb_applied + M_entorno_applied`.

### 4.2 Habitação e população atendida

Demanda ocupada urbana: `H_need_urb = round_half_up(P_urb' / household_size)`. Estoque necessário com vacância: `H_required_urb = ceil(H_need_urb / (1-vacancy_rate_target))`. Estoque após retiradas: `H_after_retirement = max(0, H_stock - round_half_up(H_stock × retirement_rate))`. Capacidade anual de construção: `C = floor(H_stock_initial × annual_capacity_rate)`. Construção: `B = min(max(0, H_required_urb - H_after_retirement), C)`. Estoque final: `H_stock' = H_after_retirement + B`. Unidades ocupáveis: `H_occ_capacity = floor(H_stock' × (1-vacancy_rate_target))`. Demanda de domicílios sem unidade: `unserved_housing_demand = max(0, H_need_urb - H_occ_capacity)`. População e estoque habitacional evoluem separadamente: a lacuna é registrada, mas não remove residentes nem bloqueia migração, pois não há dado ou regra de ação que justifique deslocamento ou barreira migratória.

### 4.3 Empregos

```text
J_total' = max(0, round_half_up(J_total × (1 + annual_growth_rate)))
```

Ratear `J_total'` pelas frações `employment.district_allocation` entre distritos urbanos, por restos maiores e empate lexicográfico. Distrito externo permanece com zero empregos. O rateio preserva soma exata; registrar `jobs_before`, `jobs_after` e `jobs_net_change`. Emprego usa parâmetro próprio e não deriva da população: não há estrutura etária, força de trabalho ou capacidade de terreno configurada para justificar esse acoplamento. A regra não afirma que empregos são ocupados por residentes, nem converte vagas em viagens.

### 4.4 Ordem, consistência e idempotência

Ordem canônica deste domínio: validar entrada → calcular fluxos demográficos → calcular estoque habitacional e demanda não atendida → calcular empregos → validar balanços → formar hash do estado candidato → commit atômico. Cada cálculo usa somente o estado candidato produzido por efeitos vencidos e por modelos anteriores declarados no contrato integrado; reprocessar a mesma identidade e conteúdo retorna o mesmo estado/hash. Nenhum agente pode editar diretamente totais derivados. `protocol_noop` mantém o estado igual e não executa estas fórmulas. `no_action` anual as executa uma vez, sem ações discricionárias.

## 5. Limites e balanços obrigatórios

- Residentes, empregos, domicílios e unidades são inteiros não negativos; taxas/frações são finitas e dentro das faixas configuradas. Para sensibilidade fora da faixa recomendada, aceitar apenas se o schema permitir limites físicos: rates de nascimento/morte `0–1`, vacância `[0,1)`, participação migratória `[0,1]`, crescimento de empregos `[-1, +∞)`.
- `P_total' = P_urb' + P_entorno'`; soma dos residentes por distrito fecha com cada subtotal e total. Recalcular totais, não armazenar cópias divergentes.
- `J_total' = Σ jobs_distrito`; empregos externos = 0.
- `H_stock' = H_after_retirement + B`; `0 ≤ B ≤ C`; retiradas não excedem estoque. `H_occ_capacity ≤ H_stock'` e `unserved_housing_demand ≥ 0`.
- Balanço demográfico auditável: `P_total' = P_total + births - deaths + M_urb_applied + M_entorno_applied`; registrar também `M_blocked` para que saldo bruto = aplicado + não aplicado. Migração é saldo assinado, e os fluxos de nascimento/morte nunca são limitados por habitação.
- Estados iniciais não mudam; cada rodada produz novo estado e referência ao hash pai. Horizonte é no máximo o configurado (padrão 10); ano sintético deve igualar `round_index`.
- Não impor limite artificial de crescimento populacional ou de emprego adicional; capacidade anual limita construções e a população sem domicílio estimado é exposta como demanda não atendida. Se qualquer política de ação futura alterar estoque ou zonas, aplicar limites após consolidar ações e antes do commit.

## 6. Dados ausentes e qualidade

1. Campos atuais obrigatórios do YAML permanecem obrigatórios e passam pelos validadores existentes. Não preencher total populacional, população distrital ou emprego inicial faltante por média externa.
2. Só `housing.initial_units` é opcional, com derivação especificada. Parâmetros de transição ausentes usam perfil padrão versionado desta especificação; ao iniciar experimento, materializar todos os defaults e registrar versão/perfil no manifesto para reprodução.
3. Ausência de distribuição `employment.district_allocation` usa quotas dos empregos urbanos iniciais; se soma inicial for zero, falhar validação em vez de ratear igualmente sem declaração.
4. Ausência de população por idade, vacância observada, unidades rurais, preços e ocupação por distrito não pode ser inferida. O protótipo usa agregados e registra a limitação; métricas dependentes desses campos ficam `unknown`/indisponíveis.
5. Valor `null`, string, NaN/infinito ou sinal/unidade desconhecida em campo numérico não equivale a ausência: rejeitar com caminho do campo. Valores negativos em estoques/fluxos absolutos rejeitar; migration e growth podem ser negativos conforme limites.
6. Fontes reais existentes no YAML não validam essas taxas nem o comportamento da transição. Não declarar calibração/validação antes de evidência observacional adequada e protocolo independente.

## 7. Critérios testáveis de aceite

1. Com perfil padrão e mesmo estado de entrada, duas execuções retornam byte a byte o mesmo payload canônico e hash.
2. `protocol_noop` preserva todos os campos e hash do estado. Uma rodada anual `no_action` executa as fórmulas exatamente uma vez e cria hash de estado distinto quando algum resultado muda.
3. Para qualquer estado válido, os totais distritais fecham população e empregos; empregos externos são zero; estoque não fica negativo; balanço de população fecha com fluxos aplicados e barrados separados.
4. Caso sem `initial_units`, preservar a referência de domicílios ocupados totais 24.104, derivar separadamente `H_occ_urb=21.069` e estoque urbano inicial `H_stock=22.178` pelo default de vacância; confirmar que entorno não recebe unidades.
5. Migração negativa nunca gera população negativa; habitação insuficiente aumenta `unserved_housing_demand` sem remover residentes.
6. Casos de crescimento de emprego negativo, zero e positivo respeitam limites e rateio determinístico; empate dos restos é resolvido por `district.id`.
7. Fronteiras de vacância 0 e próximo de 1, capacidade anual zero, estoque zero, retirement zero e demanda abaixo/acima do estoque são cobertas sem divisão por zero ou overflow silencioso.
8. Parâmetro inválido e campo obrigatório ausente falham antes de commit; ausência opcional usa derivação e registra método; `null` não é tratado como default.
9. Dez rodadas encadeadas usam estado anterior e `synthetic_year=round_index` de 1 a 10; tentativa de rodada 11 é rejeitada no horizonte padrão. A especificação não requer ou calcula score.
10. Testes cobrem cálculo inteiro, balanços, idempotência, hash do pai e atomicidade: falha na transição não publica estado parcial.

## 8. Dependências para integração

- Implementar `occupied_households_derived` total como referência existente e o estado novo de unidades urbanas em campo separado; não atribuir estoque ao entorno até haver regra explícita.
- Adicionar schema versionado e modelos estritos para parâmetros, estado evolutivo e fluxos anuais; atualizar o loader/snapshot sem alterar semântica dos campos existentes.
- Definir `transition_version`, perfil efetivamente materializado, ordenação, arredondamento, unidades, parâmetros e proveniência no manifesto do experimento/hash.
- Integrar o motor à fronteira de estado candidato de `rounds.py`; definir evento/registro para nascimentos, mortes, migração aplicada/barrada, unidades construídas/retiradas, empregos solicitados/criados/removidos e restrições aplicadas.
- Preservar snapshot inicial e hash; persistir estados por rodada e garantir commit atômico/CAS; migrar o comportamento legado para `protocol_noop` sem alterar silenciosamente seu histórico.
- Acrescentar fixtures sintéticas dedicadas e testes determinísticos para critérios da seção 7 antes de expor campos a agentes, API ou interface.
- Avaliar com usuários do modelo se as sensibilidades são úteis. Só substituir hipóteses por estimativas com dados e protocolo documentados; nenhuma fonte real é validação implícita.

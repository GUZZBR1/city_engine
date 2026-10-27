# Blueprint — cidade sintética e Urban Twin Arena

**Nome provisório da cidade:** Aurora

**Status:** arquitetura inicial para prototipação

**Versão:** 0.1

**Uso autorizado:** desenvolvimento de software, benchmark sintético e comparação experimental dentro das regras documentadas

> Aurora é uma cidade fictícia. Seus parâmetros são controlados para exercitar o sistema e não descrevem uma população, economia ou tráfego real.

## 1. Decisão de arquitetura

Construir Aurora como um laboratório sintético, pequeno e reproduzível, antes de depender de uma cidade piloto real. Ela permite implementar e verificar a cadeia completa:

**estado inicial → observação → proposta do agente → validação → transição dos modelos → métricas → registro**

O primeiro modelo funcional será mobilidade. Habitação, economia, demografia, serviços e ambiente terão contratos previstos, mas serão ativados em fases separadas. Isso evita que regras ilustrativas sejam confundidas com modelos científicos já validados.

## 2. Finalidades e limites

### Aurora pode demonstrar

- Que estados de cidade e experimentos são versionados e reproduzíveis.
- Que agentes recebem condições equivalentes e só podem propor ações permitidas.
- Que custos, restrições e efeitos de ações são aplicados de modo auditável.
- Que métricas, tradeoffs e resultados por bairro podem ser comparados em replicações.
- Que a interface e o pipeline de simulação funcionam de ponta a ponta.

### Aurora não demonstra

- Que uma política funcionará em uma cidade real.
- Que a distribuição populacional, econômica ou de tráfego representa uma população real.
- Que uma estratégia vencedora seja universalmente superior.
- Que dados gerados pelo modelo de tráfego validem independentemente esse mesmo modelo.

O projeto mantém a [ficha de validação com trânsito observado](../piloto/ficha-piloto.md) como gate empírico posterior.

## 3. Perfil urbano inicial

Aurora representa um **município sintético pequeno/médio brasileiro**, organizado em cinco distritos urbanos e um entorno rural. Para tornar “pequena/média” verificável, o perfil estatístico usa municípios de **20 mil a 500 mil habitantes** no Censo 2022. O padrão `aurora-base-v1` usa a média aritmética por município: 112.172.687 habitantes / 1.668 municípios = **67.250 habitantes**. Essa média é puxada para cima pela classe de 100–500 mil e não representa a mediana.

O IBGE registra média nacional de **2,79 moradores por domicílio ocupado**; aplicada ao perfil, resulta em aproximadamente **24.104 domicílios**. A proporção nacional urbana de 87,41% gera uma divisão de referência de **58.783 residentes urbanos** e **8.467 no entorno rural**. Essas duas proporções são proxies nacionais, não médias específicas dos municípios de 20–500 mil habitantes.

| Distrito/zona | Perfil funcional | População residente inicial | Empregos localizados |
|---|---|---:|---:|
| Centro | Administração, comércio, serviços e conexões de transporte | 8.817 | 12.000 |
| Norte Residencial | Moradia e escolas locais | 17.635 | 1.500 |
| Sul Misto | Moradia, comércio local e unidade de saúde | 14.696 | 3.500 |
| Leste Logístico | Armazéns, indústria leve e acesso de carga | 5.878 | 6.000 |
| Oeste Verde | Moradia de baixa densidade, parque e área de proteção | 11.757 | 1.000 |
| Entorno rural | População fora do núcleo urbano; viagens ligadas à cidade entram por conectores externos | 8.467 | 0 |
| **Total municipal** |  | **67.250** | **24.000** |

Os empregos são **hipótese sintética de benchmark**, não média observada por porte. A distribuição por distrito serve para criar fluxos de teste e poderá ser alterada em perfis de sensibilidade.

| Parâmetro adicional | Padrão inicial | Base e interpretação |
|---|---:|---|
| Domicílios ocupados | 24.104 | Derivado de 67.250 / 2,79 moradores; proxy nacional do Censo 2022 |
| Domicílios urbanos | 21.069 | Aproximação derivada da participação urbana nacional |
| Domicílios no entorno rural | 3.035 | Aproximação derivada da participação rural nacional |
| Área urbana modelada | 36 km² | Recorte computacional de benchmark, não média municipal |
| Densidade urbana derivada | 1.633 residentes/km² | 58.783 residentes urbanos / 36 km² |
| Empregos localizados | 24.000 | Hipótese de benchmark configurável; não inferida como média oficial |
| Orçamento por rodada | 100 créditos simulados (CS) | Unidade de jogo sem conversão para reais: 60 operação fixa, 10 reserva e 30 discricionário |
| Rodada estratégica | 1 ano sintético | Escala do experimento, sem equivalência automática com previsão anual real |

Para deslocamentos ao trabalho, a configuração inicial usa como **proxy nacional** a distribuição do Censo 2022: automóvel 32,3%, ônibus 21,4%, a pé 17,8%, motocicleta 16,4%, bicicleta 6,2% e outros 5,9%. O dado descreve o principal meio de transporte entre trabalhadores que se deslocam para o trabalho; não representa todas as viagens nem é específico para cidades pequenas/médias. Demanda de lazer, estudo e serviços permanece fora do primeiro cenário.

As faixas do IBGE são classes populacionais, não uma tipologia universal de “cidade pequena/média”. O corte de 20–500 mil é uma definição operacional deste benchmark. Se o recorte fosse 20–100 mil, a média seria aproximadamente 39.859 habitantes; guardamos essa diferença para uma futura análise de sensibilidade.

Fontes e método: [IBGE — Censo 2022, distribuição municipal por classe populacional](https://agenciadenoticias.ibge.gov.br/media/com_mediaibge/arquivos/2f5fc0ea039546721af0eacafc748718.pdf); [IBGE — população e domicílios, moradores por domicílio](https://www.ibge.gov.br/biblioteca/visualizacao/livros/liv102011.pdf); [IBGE — situação urbana e rural](https://www.ibge.gov.br/biblioteca/visualizacao/livros/liv102138.pdf); [IBGE — deslocamentos para trabalho e estudo](https://www.ibge.gov.br/estatisticas/Sociais/populacao/22827-censo-demografico-2022.html?edicao=44665); [IPEA — variação das definições de cidades médias](https://portalantigo.ipea.gov.br/agencia/images/stories/PDFs/livros/capitulo1_evolucao.pdf).

A cidade usa **créditos simulados (CS)** para orçamento e custos. Esses valores não têm conversão para moeda real. Grupos de renda, idade e mobilidade reduzida são atributos sintéticos distribuídos por configuração; os resultados são analisados por grupo e distrito para testar impactos distributivos.

## 4. Território e rede

### Forma urbana

- Área urbana modelada de 6 × 6 km, equivalente ao parâmetro de 36 km² do perfil inicial; o entorno rural é representado por zonas externas de origem/destino.
- Grade inicial de 5 × 5 cruzamentos, conectada a entradas e saídas externas.
- Centro com maior densidade de destinos e ligações de transporte.
- Zona logística com acesso dedicado para veículos pesados.
- Faixa ambiental que cria uma barreira de atravessamento entre distritos.
- Duas travessias da barreira: uma arterial e outra de capacidade menor, criando rotas alternativas e um gargalo reproduzível.

### Elementos de rede na versão inicial

- Vias arteriais, coletoras e locais, cada uma com capacidade, velocidade e permissões explícitas.
- Cruzamentos com controladores semafóricos simples e programas de tempo versionados.
- Uma linha de ônibus Leste–Centro–Oeste, com paradas e frequência definidas.
- Rede de caminhada e bicicleta simplificada, separada das faixas de tráfego motorizado.
- Entradas externas para representar viagens que começam ou terminam fora da área modelada.

### Estado da rede

Cada elemento deve incluir identificador estável, geometria, função, capacidade, condição, restrições, distrito, fonte e versão. Como a rede é sintética, seus atributos são conhecidos pela configuração. Alterações de cenário produzem um diff explícito e validável.

Uma topologia única é suficiente para testar a primeira fatia vertical. Para comparar generalização e evitar políticas que explorem só um mapa, a suíte de benchmark deverá depois incluir variantes: grade sem barreira, barreira com travessias alternativas e corredor radial. Uma variante fica reservada para avaliação e não pode ser usada no ajuste do agente.

## 5. Estado da cidade

O snapshot de uma cidade é imutável e contém:

| Domínio | Estado mínimo |
|---|---|
| Geografia | Distritos, zonas de atividade, rede e áreas protegidas |
| Demografia | População por zona e grupos sintéticos configuráveis |
| Habitação | Unidades, ocupação, capacidade e custo de construção/manutenção |
| Emprego e atividades | Empregos por setor e zona, horários e capacidade de atividade |
| Mobilidade | Rede, transporte, matriz OD sintética, modos e períodos de demanda |
| Serviços | Localização, capacidade e área de atendimento de escolas, saúde e saneamento |
| Finanças | Caixa, receita, despesa fixa, manutenção, orçamento discricionário e dívida |
| Ambiente | Áreas verdes, poluentes modelados e limites de emissão definidos no cenário |
| Regras | Zoneamento, limites de orçamento, níveis mínimos de serviço e ações permitidas |

Cada atributo possui unidade, faixa, método de inicialização, versão e etiqueta `synthetic=true`. Campos derivados são recalculados pelos modelos e não editados diretamente pelos agentes.

## 6. Demanda e cenários

### Demanda de mobilidade

A matriz origem–destino é gerada por zona, período e motivo de viagem, usando populações e empregos sintéticos. A configuração contém taxa de geração, destinos, distribuição modal, ocupação de veículos e variação por período. Todo sorteio deriva de sementes registradas.

No MVP, usar duas janelas representativas — pico da manhã e período fora de pico — com perfis simples e documentados. Resultados ficam associados a essas janelas; não são anualizados nem apresentados como contagem real diária.

### Cenários exógenos

Uma rodada pode usar um pacote versionado de condições comuns a todos os agentes:

- Demanda base, demanda alta e mudança de distribuição entre zonas.
- Fechamento de uma travessia ou redução temporária de capacidade.
- Chuva ou condição que altera velocidade e risco de interrupção.
- Crescimento populacional ou de empregos dentro de faixas sintéticas.
- Alteração de custos de energia, construção ou manutenção.

Agentes comparados recebem o mesmo cenário e semente pareada. Cenários usados para desenvolvimento ficam separados dos cenários e sementes reservados para avaliação.

## 7. Domínios e relógios de simulação

| Modelo | Escala inicial | Entradas e saídas | Implementação planejada |
|---|---|---|---|
| Mobilidade | Passos do simulador; janelas de pico | Demanda, rede e controles → tempos, fluxos, filas, acessibilidade e emissões veiculares estimadas | SUMO atrás de adaptador |
| Finanças públicas | Um passo por rodada/ano sintético | Receita e despesas → caixa, saldo, dívida e manutenção pendente | Regras contábeis transparentes |
| Habitação/uso do solo | Um passo por rodada/ano sintético | Estoque, capacidade, zoneamento e custos → novas unidades, ocupação e preço sintético | Modelo de estoque e fluxo simples, fase posterior |
| Demografia | Um passo por rodada/ano sintético | População, migração, moradia e empregos → população por zona e grupo | Regras explícitas de nascimento, mudança e migração |
| Emprego/economia | Um passo por rodada/ano sintético | Acessibilidade, oferta de empregos e cenário externo → empregos, salários e receita sintéticos | Modelo agregado, fase posterior |
| Serviços | Um passo por rodada/ano sintético | Localização e capacidade → cobertura e demanda não atendida | Modelo de área de serviço e capacidade |
| Ambiente | Por janela de mobilidade e por rodada | Emissões estimadas, áreas verdes e cenário → indicadores ambientais sintéticos | Inicialmente contabilização simplificada |
| Qualidade de vida | Derivada após os modelos | Acesso, custo, ambiente e serviços → indicadores por zona/grupo | Camada de indicadores, não agente autônomo |

**Uma rodada da Arena dura um ano sintético.** Os modelos anuais avançam uma vez por rodada. A mobilidade executa somente as janelas representativas configuradas e seus resultados são reportados para essas janelas. Um fator de expansão anual só poderá ser introduzido se sua hipótese e validação forem documentadas.

Custos e efeitos defasados são explícitos: construir infraestrutura consome orçamento na rodada de aprovação; a capacidade entra em serviço após atraso configurado; manutenção passa a ser cobrada nas rodadas seguintes.

## 8. Ações dos agentes

Agentes não editam diretamente o estado da cidade, arquivos ou simulador. Cada agente recebe uma observação documentada e devolve ações estruturadas. O árbitro valida e aplica ações como transação atômica: ou todos os efeitos válidos da rodada são aplicados segundo as regras, ou a rodada falha com motivo registrado.

### Ações do MVP

| Ação | Parâmetros principais | Custo/limite | Efeito esperado |
|---|---|---|---|
| Ajustar plano semafórico | Ciclo e divisão de verde dentro de faixa permitida | Custo operacional baixo; sem alterar hardware | Recalcula uma janela de mobilidade |
| Aumentar frequência de ônibus | Linha, frequência e duração | Orçamento recorrente por rodada | Capacidade, espera e custo de operação |
| Manutenção viária | Trecho e nível de reparo | Custo pontual e limite de obras simultâneas | Recupera capacidade/condição após atraso |
| Adicionar faixa de ônibus ou ciclovia | Corredor e segmento | Custo de obra, capacidade geométrica e aprovação | Altera rede, oferta modal e capacidade viária |

Ações de habitação, zoneamento, escola e saúde entram quando os respectivos modelos estiverem implementados. Agentes não podem inventar tipos de ação ou alterar custos. O validador recusa orçamento excedido, destino inválido, conflito de obra, violação de área protegida ou pré-condição ausente.

O registro distingue: ação proposta, validação, rejeição ou aprovação, ação aplicada, custo realizado, atraso e efeito calculado.

## 9. Arena, agentes e comparação

### Cidade padrão de partida

O benchmark inicial terá **uma cidade-base canônica**, identificada como `aurora-base-v1`. Ela é criada uma vez e permanece imutável durante cada experimento. No início da Arena, o sistema cria uma cópia independente dessa mesma cidade para cada agente; os agentes desenvolvem suas próprias cópias ao longo das rodadas.

Cada cópia começa com exatamente o mesmo snapshot: cinco distritos urbanos e entorno rural, 67.250 residentes, cerca de 24.104 domicílios, 24.000 empregos sintéticos, rede e transporte, serviços iniciais, orçamento em créditos simulados, regras, ano sintético zero e configuração de demanda. O identificador e o hash do snapshot inicial ficam registrados no experimento.

| Item | Regra de partida |
|---|---|
| Estado inicial | `aurora-base-v1`, imutável |
| Cópia por participante | Uma instância isolada por agente e outra para cada política de referência |
| Horizonte | Mesmo número de rodadas para todas as instâncias |
| Observações e ações permitidas | Mesmo contrato e limites para todos os agentes |
| Cenários externos e aleatoriedade | Compartilhados e pareados entre as cópias |
| Estado durante a execução | Independente; ações de um agente não alteram as outras cidades |

Assim, a Arena compara como diferentes estratégias **desenvolvem a mesma cidade de partida**. Agentes podem decidir ações a cada rodada; seus modelos e instruções ficam congelados durante a competição. Treinamento entre rodadas só é permitido em um modo de experimento separado e com as mesmas regras para todos.

### Participantes

- **Cinco agentes decisores** com a mesma observação, ações possíveis, orçamento e limite computacional.
- **Política de referência sem novas ações**, executada fora da competição para comparação.
- **Política simples de regra fixa**, por exemplo priorizar o trecho com maior atraso dentro de um limite de custo.
- **Árbitro**, sem objetivo competitivo, responsável por validar ações e calcular métricas.

As cinco cidades são cópias de `aurora-base-v1`. O agente e sua configuração ficam congelados durante um benchmark. Se houver aprendizagem entre rodadas, a regra aplica-se igualmente a todos e o protocolo registra estado e dados de treino.

### Ciclo de execução

1. Congelar snapshot, modelos, regras, cenário, sementes e versões dos agentes.
2. Gerar a mesma observação permitida para cada participante.
3. Receber propostas e validar todas sob as mesmas regras.
4. Resolver conflitos de ação em ordem previamente definida.
5. Aplicar ações aprovadas, avançar modelos e calcular indicadores.
6. Persistir estado, decisões, custos, resultados e incerteza da rodada.
7. Repetir em outras sementes e cenários pareados.

Uma única execução das cinco cidades demonstra a mecânica da Arena. Comparações de desempenho exigem replicações com sementes diferentes e cenários pareados; a quantidade será definida conforme a variabilidade e a diferença mínima que o experimento pretende detectar.

## 10. Dados sintéticos e referências de teste

Todo dado recebe uma classificação de proveniência:

- **Configuração sintética:** parâmetros definidos diretamente no snapshot.
- **Dado sintético gerado:** valores criados por um gerador com regra e semente documentadas.
- **Resultado simulado:** saída de um modelo versionado.
- **Observação real:** dado proveniente de fonte externa, reservado para a futura validação empírica.

Usar dois tipos de referência sintética:

1. **Casos de software com resposta conhecida:** testes pequenos de conservação de fluxo, orçamento, capacidade e transições com resultado esperado previamente especificado.
2. **Benchmarks de política sintéticos:** cenários maiores com regras explícitas, usados para comparar agentes sob hipóteses controladas.

Se SUMO gerar os mesmos dados de referência contra os quais será avaliado, o teste verifica o pipeline e a consistência interna, não a fidelidade científica do SUMO. Essa distinção deve aparecer em relatórios e interface.

## 11. Indicadores e avaliação

Apresentar um vetor de resultados por rodada, cenário, replicação, distrito e grupo:

- **Mobilidade:** tempo e atraso nas janelas modeladas, veículos atendidos, filas e acesso a destinos.
- **Finanças:** saldo, dívida, custo recorrente e manutenção pendente.
- **Habitação:** unidades disponíveis, custo de moradia sintético e deslocamento, quando esse modelo existir.
- **Serviços:** cobertura, capacidade usada e demanda não atendida.
- **Ambiente:** emissões veiculares estimadas e disponibilidade de áreas verdes.
- **Equidade:** diferenças de acesso e nível de serviço entre zonas e grupos.

Orçamento, regras de segurança e limites de capacidade são **restrições**; melhoria de mobilidade, acesso, custo e ambiente são **objetivos com tradeoffs**. O padrão é painel multidimensional com fronteira de Pareto. Uma pontuação única exige pesos explícitos, definidos antes da execução, e análise de sensibilidade.

## 12. Arquitetura de software

| Módulo | Responsabilidade inicial |
|---|---|
| `city_state` | Esquemas de snapshot, unidades, validação e migração de estado |
| `synthetic_city` | Geradores versionados de topologia, distritos, população e demanda |
| `network` | Grafo, atributos, controles, restrições e exportação para SUMO |
| `mobility` | Adaptador SUMO, executor, coleta e métricas de mobilidade |
| `domain_models` | Interfaces e modelos de finanças, habitação, demografia, economia, serviços e ambiente |
| `actions` | Schemas de ações, custos, pré-condições e aplicação transacional |
| `agents` | Interface de observação/ação e adaptadores de políticas, em sandbox |
| `arena` | Rodadas, replicações pareadas, cenários e resolução de conflitos |
| `evaluation` | Indicadores, restrições, Pareto, incerteza e relatórios |
| `experiment_registry` | Versões, proveniência, configurações, eventos e resultados |
| `api` | Contratos para cidades, experimentos, ações, jobs e resultados |
| `web` | Mapa 2D, configuração, progresso e comparação de cenários |

Dependências de infraestrutura iniciais: Python, SUMO, PostgreSQL/PostGIS, React/TypeScript, MapLibre e Docker. Persistir metadados e estados no PostgreSQL; manter grandes trajetórias como arquivos de artefato quando o volume justificar. Kaggle é ferramenta opcional de pesquisa, não fonte de verdade nem serviço de runtime.

Execuções de agentes e simuladores rodam isoladas com limites de CPU, memória, tempo, tamanho de entrada e acesso a arquivos. A API cria jobs; workers executam; o registro guarda resultados. Um broker e orquestração distribuída só entram quando benchmark demonstrar necessidade.

## 13. Critérios de aceite por MVP

### MVP 0 — cidade e mapa

- Gerar cinco distritos e rede determinística a partir de uma configuração e semente.
- Repetir a geração com a mesma versão e semente e obter o mesmo snapshot.
- Visualizar rede, distritos, travessias e destinos no mapa 2D.
- Exibir o rótulo de dados sintéticos.

### MVP 1 — mobilidade base

- Compilar a rede para SUMO e executar manhã/pico e fora de pico.
- Carregar demanda sintética com origem, destino, modo, período e semente.
- Produzir volumes, tempos, filas e relatório por trecho e distrito.
- Verificar conservação de fluxos, ausência de rotas inválidas e registro de configuração.

### MVP 2 — ações e orçamento

- Aplicar as quatro ações de mobilidade definidas no escopo ativo.
- Rejeitar orçamento insuficiente, alvos inválidos e conflitos, explicando motivo.
- Registrar custo pontual, custo recorrente, atraso e diff do cenário.
- Reproduzir cenário base e alteração com as mesmas condições externas.

### MVP 3 — primeira arena

- Executar duas políticas simples e uma referência sem ação em múltiplas sementes pareadas.
- Tratar as cinco vagas de agentes como extensão de interface, não como amostra estatística suficiente.
- Mostrar custos, resultados por dimensão, variação entre replicações e impactos por distrito.
- Não declarar vencedor universal nem esconder os pesos de eventual pontuação agregada.

### MVP 4 — crescimento urbano sintético

- Adicionar um domínio por vez com balanços explícitos, testes de invariantes e interface versionada.
- Garantir que moradia, população, emprego, orçamento e serviços não cresçam sem recursos, capacidade ou regras de transição correspondentes.
- Comparar políticas em topologias e cenários reservados.

## 14. Roadmap ajustado

1. **Bancada sintética Aurora:** mapa, rede, demanda e casos de software com resultados conhecidos.
2. **Mobilidade reproduzível:** adaptador SUMO, métricas, ações simples e experimentos pareados.
3. **Validação empírica:** completar a ficha de piloto real, importar observações independentes e declarar o domínio validado.
4. **Arena comparativa:** agentes, política de referência, execução isolada, orçamento e protocolo de avaliação.
5. **Crescimento urbano:** habitação, demografia, finanças, economia, serviços e ambiente, cada qual com dados, invariantes e validação próprios.
6. **Generalização:** múltiplas topologias, cenários ocultos, benchmarks publicados e análise de robustez.

## 15. Riscos e controles

| Risco | Controle arquitetural |
|---|---|
| Agente explora falhas de regra ou custos omitidos | Ações fechadas, custos calculados pelo árbitro, limites, invariantes e auditoria |
| Cidade sintética recompensa política específica da topologia | Família de mapas e cenários reservados para avaliação |
| Um agente parece superior por sorte | Cenários e sementes pareados, replicações e distribuição de resultados |
| Uma média esconde bairro prejudicado | Indicadores desagregados e limites mínimos por distrito/grupo |
| Estoques urbanos ficam incoerentes | Balanços de população, moradia, emprego, orçamento, serviço e manutenção |
| Benchmark é confundido com evidência real | Proveniência visível e gate separado para validação com observações reais |
| Modelos anuais e tráfego diário se misturam sem regra | Relógios separados e política explícita de agregação |

## 16. Decisões congeladas para a versão 0.1

- Cidade fictícia: **Aurora**; estado padrão imutável: **`aurora-base-v1`**.
- População padrão: **67.250 residentes**, média municipal do recorte operacional IBGE 2022 de 20–500 mil habitantes; média por domicípio, não mediana.
- Domicílios: **24.104** derivados da média nacional de 2,79 moradores por domicílio ocupado; urbanização: proxy nacional de 87,41%.
- Empregos: **24.000** como parâmetro sintético de benchmark, sem alegação de média oficial.
- Área modelada: **36 km²** e orçamento: **100 CS/rodada**, ambos parâmetros de desenho, não médias municipais.
- Cinco distritos e uma rede pequena com barreira e duas travessias.
- Rodada estratégica: um ano sintético; mobilidade roda janelas de tráfego representativas.
- Primeira versão científica: mobilidade; outros domínios começam com contratos e entram em fases posteriores.
- Avaliação padrão: vetor de indicadores, restrições e Pareto; sem score universal.
- Cinco cópias independentes de `aurora-base-v1`, uma por agente; referência sem ação e política fixa para comparação.
- Validação real permanece separada e depende de observações independentes.

## 17. Decisões futuras

- Especificar a gramática e geometria exatas da rede em arquivo de configuração.
- Definir unidades, faixas e distribuições de demanda de cada perfil sintético.
- Definir custos, atrasos, restrições e fórmula de orçamento para cada ação.
- Escolher se o primeiro agente usa política fixa, busca de parâmetros ou modelo aprendido.
- Definir o tamanho de amostra experimental após medir variabilidade e diferença mínima relevante.
- Determinar critérios para ativar modelos de habitação, demografia, economia e serviços.

## 18. Referências internas

- [Conceito de produto e arquitetura da Urban Twin Arena](../conceito/urban-twin-arena.md)
- [Ficha do piloto de reprodução do trânsito observado](../piloto/ficha-piloto.md)

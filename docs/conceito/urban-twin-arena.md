# Urban Twin Arena — conceito de produto e arquitetura

**Status:** proposta estruturada para discussão

**Versão:** 0.1

**Visão:** laboratório auditável para comparar estratégias de planejamento urbano em cidades simuladas

## 1. Resumo executivo

O Urban Twin Arena será um ambiente de experimentação no qual políticas urbanas são propostas por agentes decisores e avaliadas por modelos computacionais explícitos. Cada experimento parte de uma cidade versionada, aplica ações sujeitas a regras públicas e calcula efeitos em diferentes dimensões urbanas.

A Arena não deve afirmar que encontrou uma política universalmente superior. Ela deve responder: **sob estes dados, modelos, regras e cenários, quais resultados cada estratégia produziu, com que incerteza e para quais áreas e grupos?**

O primeiro modelo será de mobilidade e começará numa cidade sintética controlada, para desenvolver e verificar o sistema. A ficha existente de reprodução do trânsito observado será a etapa de validação empírica antes de atribuir validade a resultados sobre uma cidade real.

## 2. Objetivos e limites

### Objetivos

- Comparar estratégias sob condições iniciais, regras e hipóteses documentadas.
- Representar mobilidade e, progressivamente, outros domínios urbanos com modelos separados e verificáveis.
- Manter rastreabilidade entre observação, ação proposta, ação aplicada e resultado simulado.
- Expor tradeoffs, incerteza, impactos territoriais e limites de validade.
- Ajudar pesquisadores, planejadores e gestores a explorar alternativas antes de decisões no mundo real.

### Limites

- A Arena é ferramenta de pesquisa e apoio à decisão, não autoridade pública nem controlador de infraestrutura.
- Resultado simulado não será apresentado como medição observada.
- Validação de um submodelo não valida automaticamente os demais domínios ou suas interações.
- Uma partida ou uma única semente não sustenta um ranking robusto.
- Referenciais de indicadores não definem automaticamente pesos nem uma cidade vencedora.

## 3. Usuários e modos de uso

| Usuário | Necessidade principal |
|---|---|
| Planejador ou engenheiro urbano | Comparar alternativas e entender efeitos esperados antes de recomendar uma intervenção |
| Pesquisador ou analista | Configurar, auditar e reproduzir experimentos |
| Gestor público | Entender resultados, tradeoffs, incertezas e impactos distributivos |
| Administrador do experimento | Definir dados, regras, horizonte, agentes e protocolo de comparação |

O produto terá três modos distintos, cada um com seu próprio rótulo e critério de evidência:

1. **Validação:** comparar um modelo com observações reais numa região, período e conjunto de métricas definidos.
2. **Exploração de cenários:** testar hipóteses sem apresentar os resultados como previsões validadas.
3. **Arena comparativa:** comparar políticas ou agentes sob condições experimentais controladas e replicadas.

## 4. Ciclo de uma rodada

```text
Snapshot versionado da cidade e cenário externo
                    ↓
       Observações equivalentes aos agentes
                    ↓
       Propostas estruturadas de ação
                    ↓
 Validação de orçamento, autoridade e regras
                    ↓
 Aplicação das ações aceitas pelo árbitro
                    ↓
 Modelos urbanos atualizam estado e indicadores
                    ↓
 Registro de resultados, incerteza e novo estado
```

Uma rodada precisa declarar duração simulada, ações permitidas, se as decisões são simultâneas, como receitas e despesas evoluem e como ações com efeitos defasados são contabilizadas. O horizonte deve refletir o fenômeno estudado: investimento em habitação e infraestrutura não pode ser avaliado com a mesma escala temporal de uma operação de trânsito.

## 5. Componentes da arquitetura

| Componente | Responsabilidade |
|---|---|
| **Estado da cidade** | Snapshot versionado de população, rede, uso do solo, moradia, infraestrutura, serviços, orçamento e condições iniciais |
| **Cenários externos** | Demanda, migração, clima, economia e eventos comuns às estratégias comparadas |
| **Modelos científicos** | Atualizar partes do estado e retornar resultados, hipóteses e incerteza por domínio |
| **Agentes decisores** | Receber observações documentadas e propor ações estruturadas; não alterar diretamente o estado |
| **Validador de ações** | Verificar autoridade, orçamento, pré-condições, regras de planejamento e conflitos |
| **Orquestrador de rodadas** | Coordenar versões, ações, ordem de execução, escalas temporais e falhas |
| **Árbitro e avaliador** | Calcular indicadores independentemente dos agentes e verificar restrições obrigatórias |
| **Registro de experimentos** | Guardar dados, licenças, versões, parâmetros, ações, sementes, resultados e proveniência |
| **Interface 2D** | Mostrar mapa, evolução temporal, grupos afetados, hipóteses, incertezas e comparações |

### Domínios de modelos

- Mobilidade e transporte público.
- Uso do solo e habitação.
- População e migração.
- Economia, emprego, receita, despesas e dívida.
- Infraestrutura e serviços urbanos.
- Ambiente e emissões.
- Acessibilidade, desigualdade e qualidade de vida.

Cada domínio deve ter entradas, saídas, unidades, cobertura, intervalo temporal, versão e limites de validade explícitos. O acoplamento entre domínios também precisa ser validado; validar os módulos isoladamente não prova que seus ciclos de feedback representam a cidade.

### Escalas temporais

O orquestrador deve coordenar submodelos com frequências diferentes. O SUMO modela tráfego em escala microscópica ou mesoscópica; isso não o transforma em modelo de crescimento urbano multianual. Para rodadas anuais, mobilidade deverá fornecer agregações de períodos representativos, que alimentem os demais modelos sem simular individualmente todos os veículos do ano.

## 6. Contrato de agente e ação

O agente recebe uma observação definida pelo experimento e retorna uma proposta serializável. O ambiente e o agente não compartilham acesso de escrita ao estado científico.

Contrato mínimo de uma ação:

```json
{
  "action_id": "action-001",
  "type": "transit_service_change",
  "target": "corridor-12",
  "parameters": {
    "frequency_minutes": 8
  },
  "budget_request": 120000,
  "rationale": "Aumentar a oferta no período de pico"
}
```

O validador registra separadamente a ação proposta, os motivos de aceitação ou rejeição, o custo calculado e a ação efetivamente aplicada. Regras rígidas — como limites de orçamento e áreas protegidas — não devem ser compensáveis por uma pontuação alta em outra dimensão.

Para comparação justa, registre versão do agente, instruções, dados observáveis, ferramentas, limites de tempo e recursos computacionais. Durante uma competição, as versões dos agentes devem permanecer congeladas; aprendizado entre rodadas só pode ocorrer se for permitido a todos e estiver declarado no protocolo.

## 7. Protocolo de comparação científica

Cada experimento deve registrar e congelar:

- Snapshot inicial, dados e versões de todos os modelos.
- Regras, horizonte, orçamento e ações disponíveis.
- Informação entregue a cada agente.
- Cenários externos e sementes aleatórias.
- Versões dos agentes e limites de execução.
- Métricas, normalizações, restrições e qualquer regra de classificação.

As estratégias devem ser comparadas em **replicações pareadas**: enfrentam os mesmos cenários externos e condições aleatórias correspondentes, com múltiplas sementes. Incluir uma política de referência sem novas intervenções ou com regras fixas. Cinco cidades/agentes podem demonstrar o fluxo da Arena, mas o número de agentes não substitui replicações estatísticas.

Os resultados devem incluir distribuições ou intervalos de incerteza. Diferenças menores que a variação entre replicações não devem ser apresentadas como vantagem comprovada. Impactos devem ser desagregados por território e grupo populacional para que médias não ocultem prejuízos concentrados.

## 8. Indicadores e definição de resultado

Manter um catálogo de indicadores com nome, unidade, definição, direção desejável, método de cálculo, fonte, cobertura, incerteza, versão e licença.

As referências ISO 37120, ISO 37122 e ISO 37123 podem orientar famílias de indicadores de serviços e qualidade de vida, cidades inteligentes e resiliência; a ISO 37124:2024 orienta seu uso em conjunto. Indicadores dos ODS da ONU — incluindo o ODS 11 — e dados locais da OCDE podem fornecer contexto quando sua escala e cobertura forem adequadas. Essas referências organizam mensuração; não prescrevem uma ponderação universal para escolher a “melhor cidade”.

**Padrão de apresentação:** painel multidimensional, evolução temporal, impactos territoriais e fronteira de Pareto. Uma pontuação agregada pode ser oferecida apenas como escolha explícita do experimento, com pesos e normalizações visíveis e análise de sensibilidade da classificação.

Antes de incorporar conteúdo ou métodos protegidos das normas ISO ao software, verificar direitos de acesso, reprodução e licenciamento. A ISO informa condições específicas de licença e direitos autorais: [copyright](https://www.iso.org/copyright.html) e [termos de licença](https://www.iso.org/terms-conditions-licence-agreement.html). Também verificar os metadados e direitos de cada conjunto de dados da OCDE.

Referências oficiais:

- [ISO 37120](https://www.iso.org/standard/68498.html)
- [ISO 37122](https://www.iso.org/standard/69050.html)
- [ISO 37123](https://www.iso.org/standard/70428.html)
- [ISO 37124:2024](https://www.iso.org/standard/80290.html)
- [Indicadores globais dos ODS da ONU](https://unstats.un.org/sdgs/indicators/indicators-list/)
- [Metadados do ODS 11](https://unstats.un.org/sdgs/metadata/?Goal=11)
- [OECD Local Data Portal](https://localdataportal.oecd.org/index.html)
- [Definição da OCDE para cidades e áreas urbanas funcionais](https://www.oecd.org/en/data/datasets/oecd-definition-of-cities-and-functional-urban-areas.html)

## 9. Dados, reprodutibilidade e governança

Cada conjunto de dados deve ter origem, licença, responsável, período de validade, resolução, qualidade, limitações e transformações registradas. Distinguir dados observados, estimados e sintéticos no armazenamento, nas APIs, nos mapas e nos relatórios.

Cada resultado deve poder apontar para o estado inicial, agente, ações, modelos, parâmetros, dados, sementes e código de métricas usados. Processos de simulação e agentes devem rodar isolados, com limites de CPU, memória, duração e acesso a arquivos. Aplicar controle por organização e projeto, auditoria e minimização de dados de mobilidade conforme a LGPD.

## 10. Estratégia tecnológica incremental

### Base do primeiro ciclo

- **Python** para domínio, modelos e orquestração científica.
- **SUMO** como primeiro modelo de tráfego, por trás de um adaptador.
- **PostgreSQL/PostGIS** para estado, geometrias, experimentos e metadados.
- **React + TypeScript + MapLibre** para interface 2D.
- **Docker** para execução isolada e desenvolvimento reproduzível.

### Entrar apenas quando justificado

- **PyTorch** após existir problema de aprendizagem, dados suficientes e ganho mensurável frente a uma política de referência.
- **Gymnasium/PettingZoo** se o desenho exigir uma API de aprendizado por reforço ou um ambiente multiagente padronizado; os agentes da Arena podem começar por um contrato de política próprio e simples.
- Broker, Redis, armazenamento de objetos e Kubernetes quando carga, distribuição ou operação os exigirem.
- Kaggle como fonte opcional de descoberta e experimentação, nunca como registro de proveniência ou garantia de licença dos dados incorporados.

O SUMO é adequado para mobilidade, mas não substitui modelos de habitação, economia, população ou evolução urbana. A seleção e o acoplamento desses modelos são decisões científicas futuras, não componentes presumidos da primeira entrega.

## 11. Roteiro de evolução

### Etapa 1 — Construir a bancada sintética

Criar Aurora como uma cidade fictícia versionada, com rede, demanda e casos de referência conhecidos. Usá-la para verificar o mapa, a execução reprodutível, o contrato de ações e a mecânica da Arena. Resultados desta etapa são sintéticos.

### Etapa 2 — Validar a linha de base de mobilidade

Executar a ficha atual de [reprodução do trânsito observado](../piloto/ficha-piloto.md): delimitar região e período, verificar dados, revisar a rede, calibrar e comparar com observações independentes. Se faltarem dados, limitar a entrega à demonstração técnica e rotular resultados como exploratórios.

### Etapa 3 — Testar uma intervenção viária

Adicionar uma ação simples, seu custo e pré-condições. Comparar cenário base e intervenção com entradas equivalentes, replicações e efeitos nas vias próximas.

### Etapa 4 — Primeira arena controlada

Executar duas políticas simples e uma política de referência, no mesmo estado inicial e em replicações pareadas. Depois demonstrar cinco agentes como experiência de produto, sem tratar cinco execuções únicas como benchmark estatístico.

### Etapa 5 — Ampliar modelos urbanos

Incorporar domínios somente com variáveis, dados, unidades, escalas temporais, interfaces e protocolos de validação definidos. Validar também as interações entre os modelos.

### Etapa 6 — Benchmark e pesquisa

Versionar benchmarks, cenários e regras; oferecer análises robustas a diferentes futuros e publicar resultados, limites, incertezas e critérios de comparação.

## 12. Critérios para avançar de etapa

- **Mobilidade → intervenção:** rede e linha de base possuem cobertura e validação suficientes para a pergunta pretendida.
- **Intervenção → arena:** ações, regras, custos, observações, árbitro e registro de experimento têm contratos versionados.
- **Arena → ranking comparativo:** existem replicações, cenários comuns, baseline, incerteza e protocolo de classificação pré-definido.
- **Mobilidade → outro domínio:** há dados e modelo documentados, validação independente e definição explícita de como o domínio troca estado com os demais.

Se um gate não for cumprido, o sistema pode continuar útil para exploração técnica, mas deve restringir as alegações de validade e comparação.

## 13. Decisões em aberto

1. Qual caso de uso de mobilidade será a primeira intervenção após validar a linha de base?
2. Qual cidade e área têm dados observados, autorização de uso e parceiro técnico disponíveis?
3. Qual é a duração simulada de uma rodada e como os domínios avançam em frequências diferentes?
4. Quais decisões os agentes podem tomar e quais restrições são invioláveis?
5. O experimento compara políticas com objetivos selecionados por cada usuário ou terá um perfil de avaliação padrão?
6. Quais grupos e unidades territoriais serão usados para avaliar distribuição de impactos?
7. Quem define pesos, normalizações e horizonte, e como as escolhas ficam auditáveis?
8. Quais modelos de habitação, economia, população e ambiente serão avaliados para fases futuras?

## 14. Princípio de comunicação

Usar formulações como: **“neste experimento, com estes dados, modelos, restrições e cenários, a estratégia A apresentou estes resultados e esta incerteza em comparação com a referência.”**

Evitar afirmar que um agente descobriu a melhor política para qualquer cidade ou que o resultado simulado garante um efeito no mundo real.

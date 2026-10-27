# MVP 1 — Prompts e comandos para quatro chats

Este documento divide a próxima etapa em quatro frentes com ownership separado. O objetivo é executar uma simulação-base reproduzível de Aurora no SUMO e apresentar seus resultados. **Agentes de IA, otimização e intervenções ficam fora deste MVP.**

## Como usar

1. Abra quatro chats no mesmo projeto e workspace.
2. Cole um prompt por chat, na ordem abaixo. Comece pelo Chat 1; o Chat 2 depende do contrato de rede e demanda que ele produzir.
3. O Chat 3 depende da interface do simulador definida pelo Chat 2. O Chat 4 pode preparar a interface usando o contrato HTTP deste documento enquanto os Chats 2 e 3 trabalham.
4. Ao concluir as frentes, use este chat como integrador: confira os contratos, rode a API e o frontend e valide uma execução do início ao resultado.

Cada chat deve usar pelo menos dois subagentes nativos, com `agent_type` explícito: um para revisar desenho/contratos e outro para verificar critérios. Os revisores ficam em leitura apenas; o chat responsável faz as alterações e integra os achados. Se a interface não oferecer roteamento nativo por `agent_type`, prossiga sem fingir o papel e informe a limitação.

## Ownership e dependências

| Chat | Responsabilidade | Ownership exclusivo | Dependência |
|---|---|---|---|
| 1 — Rede e demanda | Completar a cidade sintética com parâmetros viários e demanda OD | `configs/cities/aurora-base-v1.yaml`, `packages/urban_arena/` | MVP 0 integrado |
| 2 — Motor SUMO | Adaptador, compilação da rede, execução determinística e métricas | `packages/simulation/` | Contrato entregue pelo Chat 1 |
| 3 — API | Criar job de simulação e consultar status/resultados | `apps/api/` | Interface entregue pelo Chat 2 |
| 4 — Interface | Acionar execução e apresentar status/resultados | `apps/web/` | Contrato HTTP fixado abaixo; integração final com Chat 3 |

Não deixe dois chats editar a mesma pasta. Se for necessária uma mudança fora do ownership, registre a proposta para o integrador em vez de alterar os arquivos do outro chat.

---

## Chat 1 — Rede viária e demanda sintética

```text
Implemente a preparação dos dados de Aurora para a primeira simulação-base da Urban Twin Arena.

Leia AGENTS.md, `docs/execucao/prompts-mvp1-4-chats.md`, `docs/execucao/prompts-mvp0-3-chats.md`, `docs/arquitetura/arquitetura-completa-urban-twin-arena.md`, `docs/arquitetura/cidade-sintetica-urban-twin-arena.md` e `configs/cities/aurora-base-v1.yaml`. Confira o código atual antes de alterar qualquer coisa.

Ownership exclusivo:
- `configs/cities/aurora-base-v1.yaml`
- `packages/urban_arena/`
- Não edite `packages/simulation/`, `apps/api/` ou `apps/web/`.

Entregue:
1. Parâmetros explícitos de vias necessários ao SUMO, incluindo velocidade, número de faixas, capacidade/fluxo e classe da via.
2. Controladores e tempos semafóricos iniciais para os cruzamentos que forem sinalizados.
3. Demanda OD sintética para as janelas existentes, com regras, unidades e semente documentadas.
4. Schemas tipados, validações de consistência e acesso aos novos dados pelo pacote `urban_arena` sem duplicar valores em código.
5. Um contrato Python estável e um exemplo serializado que o Chat 2 possa consumir sem importar internals do pacote.

Restrições:
- Marque todos os valores sintéticos como hipóteses de benchmark; não os apresente como medições ou médias reais.
- Não altere população, orçamento ou outros totais sem justificativa explícita.
- Respeite as duas travessias atuais da barreira e a malha de 74 arestas direcionadas.
- Não implemente SUMO, API, interface, IA ou otimização.
- Preserve a geração determinística e a proveniência/hash do snapshot.

Critérios de entrega:
- YAML inválido ou parâmetros incompatíveis falham com mensagens úteis.
- Rede e demanda carregam com unidades e IDs estáveis.
- O contrato exportado é suficiente para compilar rede e rotas no SUMO.
- Informe arquivos, hipóteses sintéticas, contrato para o Chat 2 e verificações executadas.

Antes de editar, use subagentes nativos em leitura apenas: `architect` para revisar o modelo de dados e `verifier` para revisar balanços e critérios. Passe `agent_type` explicitamente.
```

## Chat 2 — Adaptador SUMO e simulação-base

```text
Implemente o motor da primeira simulação-base de Aurora com SUMO, consumindo o contrato publicado pelo Chat 1. Não replique os dados da cidade nem acople SUMO ao domínio central.

Leia AGENTS.md, `docs/execucao/prompts-mvp1-4-chats.md` e as arquiteturas do projeto. Inspecione o contrato de rede/demanda produzido pelo Chat 1. Antes de escolher a forma de execução, confira a disponibilidade e a versão de SUMO no ambiente; não presuma que está instalado.

Ownership exclusivo:
- `packages/simulation/`
- Não edite `packages/urban_arena/`, `configs/`, `apps/api/` ou `apps/web/`.

Entregue:
1. Interface de engine independente de SUMO e adaptador SUMO isolado.
2. Compilação dos dados de Aurora para arquivos de rede e rotas exigidos pelo SUMO.
3. Runner de uma janela configurada, com semente fixa, limites de execução e cancelamento quando viável.
4. Coleta de métricas: viagens solicitadas/concluídas, tempo médio de viagem, velocidade média, fila ou proxy explicitamente definido e avisos de execução.
5. Resultado tipado com IDs/versões de entrada, semente, versão do simulador, métricas e referências a artefatos.
6. Adaptador invocável pela API através de uma interface Python estável.

Restrições:
- Não invente métricas quando o SUMO não as fornecer; declare método e limitações de cada indicador.
- Não afirme que a simulação foi validada com dados reais. Aurora e a demanda são sintéticas.
- Não implemente workers distribuídos, filas externas, banco, otimização ou agentes treináveis.
- Não instale binários do sistema sem necessidade; documente uma alternativa local/containerizada se SUMO não estiver disponível.

Critérios de entrega:
- Uma execução base termina e produz resultado reproduzível para mesmas entradas, versão e semente.
- Falhas de configuração, timeout e erro do SUMO são retornados com mensagem estável.
- O pacote pode ser chamado sem FastAPI.
- Informe comandos, versão/disponibilidade do SUMO, métricas, arquivos e verificações.

Antes de editar, use subagentes nativos em leitura apenas: `researcher` para consultar documentação oficial atual do SUMO e `architect` ou `verifier` para revisar o adaptador e a reprodutibilidade. Passe `agent_type` explicitamente; não substitua a pesquisa oficial por memória.
```

## Chat 3 — API de jobs e resultados

```text
Estenda a API existente para solicitar a simulação-base de Aurora e consultar status e resultados, usando a interface pública do pacote `packages/simulation/`.

Leia AGENTS.md, `docs/execucao/prompts-mvp1-4-chats.md`, `apps/api/README.md` e os contratos efetivamente entregues pelos Chats 1 e 2. Preserve os endpoints atuais de saúde, metadados e mapa.

Ownership exclusivo:
- `apps/api/`
- Não edite `packages/urban_arena/`, `packages/simulation/`, `configs/` ou `apps/web/`.

Contrato inicial esperado:
- `POST /api/v1/simulations` — solicita uma execução base; recebe `city_id`, janela e semente opcional; retorna `simulation_id` e status inicial.
- `GET /api/v1/simulations/{simulation_id}` — retorna status e, quando concluído, métricas e metadados do resultado.
- `POST /api/v1/comparisons` — cria comparação pareada entre base e intervenção semafórica declarativa.
- `GET /api/v1/comparisons/{comparison_id}` — retorna status, parâmetros comuns, identidades dos resultados, métricas e deltas intervenção menos base.
- `POST /api/v1/simulations/{simulation_id}/cancel` — cancelar, se suportado pela interface do engine.

Contrato JSON compartilhado para API e frontend. O corpo de `POST` é:

```json
{
  "city_id": "aurora-base-v1",
  "window_id": "peak_am",
  "seed": 42,
  "drain_limit_seconds": 3600
}
```

Resposta `202` do `POST` e resposta `200` do `GET`:

```json
{
  "simulation": {
    "simulation_id": "<id>",
    "status": "queued",
    "city_id": "aurora-base-v1",
    "snapshot_id": "aurora-base-v1:<hash>",
    "window_id": "peak_am",
    "seed": 42,
    "drain_limit_seconds": 3600,
    "engine_version": "<version>",
    "metrics": null,
    "warnings": []
  }
}
```

Os estados permitidos são `queued`, `running`, `succeeded`, `failed` e `cancelled`. Em sucesso, `metrics` contém `trips_requested`, `trips_completed`, `trips_not_completed`, `mean_travel_time_seconds`, `mean_speed_kmh` e `mean_queue_length_meters`; os totais de viagens devem reconciliar (`trips_requested = trips_completed + trips_not_completed`). Médias podem ser `null` quando indisponíveis. A fila é comprimento em metros, não quantidade de veículos. As solicitações devem retornar `drain_limit_seconds` (padrão de 3600 s); as partidas ficam restritas à janela de demanda, e o escoamento pode ultrapassá-la. As métricas de duração e velocidade cobrem viagens concluídas até o fim do escoamento, enquanto a fila média cobre somente a janela de demanda. Em falha ou cancelamento, mantenha `metrics: null` e retorne um erro estável; não invente resultados parciais. O `seed` deve ser devolvido inclusive quando foi escolhido pelo servidor.

Uma comparação carrega a entrada da cidade uma vez e deriva dela ambos os cenários. A demanda expandida, snapshot, janela, semente e `drain_limit_seconds` devem ser idênticos. O cenário demonstrativo altera somente as durações das quatro fases de `node:02:00` para `40, 3, 20, 3` s, preservando movimentos, ordem e ciclo de 66 s. Rejeite nó/controlador inexistente, quantidade ou ordem incorreta de fases, durações não positivas e ciclo alterado. Não altere YAML. Se qualquer execução falhar, a comparação é `failed` e não publica métricas nem deltas parciais.

Requisitos:
- Não executar a simulação dentro do ciclo síncrono da requisição HTTP.
- Para MVP local, pode usar executor em processo se isso for compatível com a API atual; documente que jobs não são duráveis após reinício e esconda a implementação atrás de uma interface.
- Validar janela, cidade e semente; retornar erros HTTP e schemas OpenAPI explícitos.
- Não adicionar banco, broker, login ou endpoint que acione infraestrutura real.
- Não recalcular métricas que pertencem ao pacote de simulação.

Critérios de entrega:
- A API permite criar, consultar e concluir uma execução de Aurora.
- Status, erros e resultado obedecem a schemas estáveis.
- API continua servindo corretamente os endpoints do MVP 0.
- Informe comandos, contratos, arquivos e verificações executadas.

Antes de editar, use subagentes nativos em leitura apenas: `architect` para revisar fluxo e fronteiras e `verifier` para revisar contratos HTTP e erros. Passe `agent_type` explicitamente.
```

## Chat 4 — Interface para executar e comparar resultados

```text
Estenda o frontend existente para iniciar a simulação-base de Aurora e uma comparação pareada de temporização semafórica, acompanhar seus status e mostrar as métricas retornadas pela API.

Leia AGENTS.md, `docs/execucao/prompts-mvp1-4-chats.md` e `apps/web/README.md`. Preserve o mapa e a indicação de que Aurora e seus dados são sintéticos. Consuma apenas a API; não importe o pacote Python nem calcule resultados científicos no navegador.

Ownership exclusivo:
- `apps/web/`
- Não edite `apps/api/`, `packages/`, `configs/` ou os contratos no backend.

Entregue:
1. Ação explícita para iniciar a simulação base usando o `city_id` e uma janela disponível.
2. Estados acessíveis de envio, execução, conclusão, cancelamento e erro, com nova tentativa quando aplicável.
3. Painel de resultados com valores, unidades e descrição dos indicadores vindos da API.
4. Identificação do snapshot, semente e estado sintético da execução.
5. Tratamento para API indisponível, resposta incompleta e execução falha, sem apresentar valores antigos como atuais.
6. Comparação lado a lado entre base, intervenção e delta intervenção menos base, incluindo unidades, semente, snapshot, janela e avisos por cenário; sem score agregado.

Restrições:
- Sem agente de IA, pontuação competitiva, otimização ou animação de veículos nesta etapa. A única intervenção editável é a temporização declarativa descrita acima.
- Não transformar métricas em resultados reais ou validados.
- Não persistir dados ou simulações no navegador.
- Use os contratos HTTP deste arquivo como referência e ajuste apenas o cliente frontend quando o schema final da API mudar.

Critérios de entrega:
- Usuário inicia uma simulação e acompanha até o resultado ou erro.
- Resultado exibe unidades, semente e snapshot correspondente.
- Interface funciona com API local e mantém acessibilidade e estados do MVP 0.
- Informe comandos, arquivos e verificações executadas.

Antes de editar, use subagentes nativos em leitura apenas: `designer` para revisar interação/acessibilidade e `verifier` para revisar os estados e o consumo do contrato. Passe `agent_type` explicitamente.
```

---

## Comandos locais após a integração

Execute a partir da raiz do projeto. Crie o ambiente virtual apenas se ainda não existir. O Chat 2 deve documentar como instalar/ativar SUMO no ambiente; não assuma que a instalação do Python instala o executável `sumo`.

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ./packages/urban_arena -e ./packages/simulation -e ./apps/api
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
```

Em outro terminal, para iniciar o frontend:

```bash
cd apps/web
npm install
npm run dev
```

O frontend usa `http://127.0.0.1:8000` por padrão. Use `VITE_API_BASE_URL` em `apps/web/.env.local` se a API estiver em outro endereço. Os chats devem atualizar os READMEs com quaisquer comandos finais diferentes destes.

## Integração final

O integrador confere, nesta ordem: contrato de rede/demanda → execução direta do motor → endpoints e OpenAPI → fluxo visual até exibir métricas. Registre versões, semente, snapshot e proveniência. Não chame o modelo calibrado ou validado sem comparação com observações independentes.

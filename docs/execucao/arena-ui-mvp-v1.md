# MVP de interface — Arena anual Aurora

## Objetivo

Conectar a Arena anual já exposta pela API à interface React existente. O usuário poderá iniciar uma execução sintética de Aurora, acompanhar as rodadas e inspecionar cinco instâncias e seus indicadores.

Este MVP demonstra o fluxo anual. As cinco instâncias usam políticas determinísticas de referência sem ações (`no_action`); não há comparação entre estratégias, vencedor, pontuação agregada ou previsão validada de uma cidade real.

## Contrato existente da API

- `POST /api/v1/arenas`, corpo `{ "horizon_rounds": 1..10 }`, retorna HTTP 202 com `{ "arena": ArenaJob }` em estado `queued`.
- `GET /api/v1/arenas/{arena_id}` retorna `{ "arena": ArenaJob }`; ID desconhecido retorna 404.
- Estados terminais: `succeeded` e `failed`. Estados ativos: `queued` e `running`.
- `committed_rounds` conta rodadas confirmadas pelo motor; `completed_rounds` conta rodadas com detalhes serializados e publicados. Sempre validar `0 <= completed_rounds <= committed_rounds <= horizon_rounds`.
- Uma rodada publicada contém exatamente cinco instâncias. Após erro de serialização, a Arena pode estar `failed`, com `committed_rounds > completed_rounds`, estados detalhados nulos e hashes/índices confirmados disponíveis.
- Os jobs são process-local; reiniciar a API perde o acompanhamento. Não existe cancelamento nem endpoint de listagem.

## Arquitetura do frontend

1. **Cliente/contratos (`src/arenaApi.ts`)** — tipos da resposta HTTP, validação em runtime, `startArena(horizonRounds)` e `fetchArena(arenaId)`. Não expor `unknown` ou dataclasses do backend à interface sem validação.
2. **Painel visual (`src/ArenaPanel.tsx` e CSS próprio)** — formulário de horizonte, estado/progresso, cinco instâncias e resultados por rodada. Recebe dados e callbacks por props; não faz chamadas HTTP diretamente.
3. **Integração e QA (`src/App.tsx` e adaptador de view model)** — conectar cliente e painel, controlar polling, proteger contra respostas antigas após nova tentativa e testar os contratos transformados. Esta frente começa após as duas primeiras serem integradas ao ramo-base.

O cliente API retorna o DTO validado. Um adaptador separado transforma esse DTO no modelo visual do painel. Isso mantém o componente independente do formato HTTP e evita duplicar parsing.

## Fluxo e estados

`idle → submitting → queued/running → succeeded/failed`

- Horizonte padrão: 10; intervalo permitido: 1 a 10.
- Fazer polling a cada 1,5 s somente enquanto `queued` ou `running`; parar em estado terminal ou erro de consulta.
- Desabilitar início enquanto o POST estiver pendente ou a Arena estiver ativa. Uma nova tentativa invalida respostas pendentes da tentativa anterior.
- Se `failed`, manter visíveis as rodadas publicadas anteriormente; nunca inventar detalhes da rodada incompleta.
- Se `committed_rounds` exceder `completed_rounds`, explicar que o motor confirmou estado, mas os detalhes não foram publicados. Exibir os hashes/índices confirmados disponíveis.
- Mostrar `null_reason` para indicadores indisponíveis; não substituir `null` por zero.

## Apresentação

- Cabeçalho fixo: “Arena anual · Aurora sintética” e aviso de política de referência sem ações.
- Progresso: status em linguagem simples, `completed_rounds` de `horizon_rounds`, `committed_rounds` separado, e ID da Arena.
- Resultados: seletor de rodada e tabela acessível com cinco instâncias. Agrupar população, habitação, empregos, serviços, área verde e indicadores disponíveis com unidade e período.
- Detalhes recolhíveis: hashes do snapshot, manifesto e estados; não sobrecarregar a visão inicial.
- Não ordenar por desempenho, destacar uma instância como vencedora nem agregar score.

## Responsabilidades por chat/branch

- **Chat 1 — Cliente e contrato API**, branch filha `feature/aurora-arena-ui-api`: `src/arenaApi.ts` e testes unitários próprios. Não edita `App.tsx` nem componentes visuais.
- **Chat 2 — Painel da Arena**, branch filha `feature/aurora-arena-ui-screen`: `src/ArenaPanel.tsx` e CSS próprio; componente recebe props tipadas e callbacks, sem importar o cliente nem editar `App.tsx`.
- **Chat 3 — Integração e QA**, branch filha `feature/aurora-arena-ui-integration`: começa quando os chats 1 e 2 estiverem integrados ao ramo-base; edita `App.tsx`, adaptador de view model e testes de integração da UI. Não redefine contrato ou estilos do painel.

Todos os chats devem usar agentes especialistas para revisão/testes quando isso ajudar, manter ownership de arquivos, preservar mudanças alheias e fazer commits locais sem push. O coordenador integra os ramos, resolve conflitos e executa a validação final.

## Critérios de aceite

- Iniciar Aurora sintética com horizonte válido de 1–10 e receber resposta 202.
- Validar o contrato e acompanhar o job até estado terminal; polling para ao concluir/falhar.
- Mostrar cinco instâncias por rodada publicada e todas as unidades/metadados disponíveis.
- Tratar falha HTTP, falha de rede, resposta inválida, 404 e falha de serialização sem perder rodadas completas nem aceitar resposta obsoleta.
- Acessibilidade por teclado, rótulo associado ao seletor, status anunciado a leitor de tela, barra de progresso semântica e tabela com cabeçalhos.
- Rotular a proveniência sintética e `no_action`; não exibir score ou conclusão científica.
- `npm test` e `npm run build` passam após a integração das três frentes.

## Fora do escopo

Persistência/cancelamento de jobs, novas políticas de agente, ações executáveis, integração de semáforos com SUMO, mapas de estado anual e comparação científica entre estratégias. Essas entregas vêm depois de o fluxo visual básico estar integrado.

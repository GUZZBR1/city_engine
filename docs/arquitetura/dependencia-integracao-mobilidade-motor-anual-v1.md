# Dependência de integração: mobilidade do motor anual Aurora v1

**Status:** proposta de handoff; depende do runner anual e da decisão do coordenador.

## Estado encontrado nesta branch

O contrato integrado define mobilidade SUMO somente para janelas configuradas e
proíbe anualizar os resultados. O pacote `simulation` já expõe
`run_simulation(...)`, `SimulationInput`, `SimulationResult` e `SimulationError`.
O resultado contém `window_id`, semente, métricas, métodos, avisos e artefatos.
`run_simulation` valida que `inputs.window.id` corresponde à janela solicitada.

A API já oferece `SimulationRequest`, `SimulationJob`, `POST /api/v1/simulations`
e `GET /api/v1/simulations/{simulation_id}` para jobs em memória do snapshot-base.
Este checkout não contém um runner anual nem um handoff compartilhado entre ele
e a API. O job HTTP atual não recebe estado candidato ou uma ação semafórica.

## Proposta mínima compatível

1. O runner anual continua dono do manifesto, da rodada e do `RoundResult`.
2. Para uma execução de mobilidade solicitada, o runner fornece ao adaptador uma
   `SimulationInput` da janela configurada e usa o mesmo `window_id`; para a ação
   semafórica v1, mapeia a ação validada para o `SignalTimingIntervention` já
   existente.
3. O adaptador retorna o `SimulationResult` atual, identificado por janela. O
   runner registra a referência e a proveniência da janela no resultado anual;
   não multiplica, extrapola nem converte essas métricas em indicadores anuais.
4. Se a execução precisar passar pela API, estender o `SimulationRequest` e o
   `run_job` existentes para aceitar a intervenção opcional e encaminhá-la a
   `run_simulation`. Reutilizar `SimulationJob` para status, métricas da janela e
   erro codificado. Não criar um segundo schema de job ou resultado SUMO.

O item 4 é uma proposta, não foi implementado nesta branch: falta o runner que
define quando uma ação aprovada vira job e como a referência do job fica ligada
à rodada. A implementação deve ocorrer junto ao contrato de chamada do runner,
para manter uma única fonte de identidade e evitar aceitar uma ação sem execução
configurada. Até essa dependência ser resolvida, o job HTTP existente continua
limitado ao snapshot-base.

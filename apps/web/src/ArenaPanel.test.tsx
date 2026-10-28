import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ArenaPanel, type ArenaPanelViewModel } from './ArenaPanel';

describe('ArenaPanel action evidence', () => {
  it('shows accessible, scoped SUMO comparison with deterministic benchmark wording', () => {
    const viewModel = {
      arenaId: 'arena-1', status: 'succeeded', horizonRounds: 1, committedRounds: 1, completedRounds: 1,
      manifest: { hash: 'manifest', snapshotId: 'snapshot-1', snapshotHash: 'snapshot-hash', profileId: 'reference', profileVersion: '1',
        parameterVersion: '1', schemaVersion: '1', generatorVersion: '1', transitionVersion: '1', catalogVersion: '1', rulesVersion: '1',
        provenance: 'synthetic', parameters: {}, seeds: { base: 42 } },
      instances: [{ instanceId: 'instance-1', agentId: 'agent-1', policyId: 'signal_heuristic', policyVersion: '1', currentRoundIndex: 1,
        currentCityStateHash: 'state', initialCityStateHash: 'initial', currentState: null }],
      rounds: [{ roundIndex: 1, instances: [{ instanceId: 'instance-1', observedCityStateHash: 'observed', parentCityStateHash: 'parent',
        cityStateHash: 'state', manifestHash: 'manifest', roundRecordHash: 'record', decision: 'accepted', metrics: [], actionExecutionEvidence: {
          executorId: 'sumo-arena-signal-v1', evidenceType: 'paired_sumo_window_comparison', actionIds: ['action-1'], windowId: 'weekday-am', seed: 42,
          engine: 'SUMO', engineVersion: '1.20', snapshotId: 'snapshot-1', snapshotHash: 'snapshot-hash', routeExposure: 'not_exposed', limitations: ['Nenhuma rota passa no nó.'], baseSimulationId: 'base',
          interventionSimulationId: 'intervention', baseMetrics: { trips_completed: 8, mean_travel_time_seconds: 120, mean_speed_kmh: 24, mean_queue_length_meters: 8,
            trips_requested: 10, trips_not_completed: 2 }, interventionMetrics: { trips_completed: 9, mean_travel_time_seconds: 110, mean_speed_kmh: 26,
            mean_queue_length_meters: 6, trips_requested: 10, trips_not_completed: 1 }, deltas: { trips_completed: 1, mean_travel_time_seconds: -10,
            mean_speed_kmh: 2, mean_queue_length_meters: -2, trips_requested: 0, trips_not_completed: -1 },
        }, signalTargetIds: ['node:02:04'] }] }], error: null,
    } as unknown as ArenaPanelViewModel;
    const html = renderToStaticMarkup(createElement(ArenaPanel, { viewModel, horizonRounds: 1, onHorizonChange: vi.fn(), onStart: vi.fn() }));
    expect(html).toContain('políticas determinísticas de benchmark');
    expect(html).toContain('não são agentes treinados e não tomam decisões autônomas');
    expect(html).toContain('um baseline sem ação e quatro heurísticas semafóricas');
    expect(html).toContain('cinco referências sem ação');
    expect(html).toContain('a ausência de evidência SUMO, por si só, não confirma que o motor estava indisponível');
    expect(html).toContain('PARTICIPANTES');
    expect(html).toContain('Cruzamento</dt><dd>node:02:04');
    expect(html).toContain('Janela</dt><dd>weekday-am');
    expect(html).toContain('SIMULADA e sintética');
    expect(html).toContain('uma única janela');
    expect(html).toContain('nem os misture com indicadores urbanos anuais');
    expect(html).toContain('Baseline');
    expect(html).toContain('Intervenção');
    expect(html).toContain('Delta');
    expect(html).toContain('Velocidade média');
    expect(html).toContain('Fila média');
    expect(html).toContain('Hash do snapshot');
    expect(html).toContain('nenhuma rota solicitada passa pelos nós alterados');
    expect(html).toContain('Nenhuma rota passa no nó.');
    expect(html).toContain('aria-label="Métricas da comparação SUMO de instance-1"');

    const legacyHtml = renderToStaticMarkup(createElement(ArenaPanel, {
      viewModel: { ...viewModel, rounds: [] }, horizonRounds: 1, onHorizonChange: vi.fn(), onStart: vi.fn(),
    }));
    expect(legacyHtml).toContain('Cinco políticas de referência');
    expect(legacyHtml).toContain('não são agentes treinados e não tomam decisões autônomas');
    expect(legacyHtml).not.toContain('Comparação SUMO por instância');
  });
});

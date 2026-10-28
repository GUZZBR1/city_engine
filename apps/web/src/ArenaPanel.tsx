import { useState, type FormEvent } from 'react';
import './ArenaPanel.css';

export type ArenaPanelStatus = 'idle' | 'submitting' | 'queued' | 'running' | 'succeeded' | 'failed';

export interface ArenaPanelMetric {
  id: string;
  label: string;
  value: number | null;
  unit: string;
  unitBasis?: string;
  period: string;
  nullReason?: string | null;
}

export interface ArenaPanelCityState {
  roundIndex: number;
  cityStateHash: string;
  parentCityStateHash?: string | null;
  population?: { total: number; urban: number; ruralCatchment: number };
  housing?: { totalUnits: number; occupiedHouseholds: number; vacancyRate: number };
  employment?: { totalJobs: number };
  services?: {
    schoolDemand: number;
    schoolCapacity: number;
    primaryHealthDemand: number;
    primaryHealthCapacity: number;
  };
  publicGreenAreaM2?: number;
}

export interface ArenaPanelInstance {
  instanceId: string;
  agentId: string;
  policyId: string;
  policyVersion: string;
  currentRoundIndex: number;
  currentCityStateHash: string;
  initialCityStateHash: string;
  currentState: ArenaPanelCityState | null;
}

export interface ArenaPanelRoundInstance {
  instanceId: string;
  observedCityStateHash: string;
  parentCityStateHash: string;
  cityStateHash: string;
  manifestHash: string;
  roundRecordHash: string;
  decision: 'accepted' | 'rejected' | 'no_action';
  metrics: ArenaPanelMetric[];
  actionExecutionEvidence?: ArenaPanelActionExecutionEvidence | null;
  signalTargetIds?: string[];
}

export interface ArenaPanelActionExecutionEvidence {
  executorId: string;
  evidenceType: string;
  actionIds: string[];
  windowId: string;
  routeExposure: 'exposed' | 'not_exposed' | 'unknown';
  seed: number;
  engine: string;
  engineVersion: string;
  snapshotId: string;
  snapshotHash: string;
  baseSimulationId: string;
  interventionSimulationId: string;
  baseMetrics: Record<string, number | null>;
  interventionMetrics: Record<string, number | null>;
  deltas: Record<string, number | null>;
  limitations: string[];
}

export interface ArenaPanelRound {
  roundIndex: number;
  instances: ArenaPanelRoundInstance[];
}

export interface ArenaPanelManifest {
  hash: string;
  snapshotId: string;
  snapshotHash: string;
  profileId: string;
  profileVersion: string;
  parameterVersion: string;
  schemaVersion: string;
  generatorVersion: string;
  transitionVersion: string;
  catalogVersion: string;
  rulesVersion: string;
  provenance: string;
  parameters: Record<string, unknown>;
  seeds: Record<string, number>;
}

/** Presentation-ready data. The integration layer adapts the validated API DTO into this shape. */
export interface ArenaPanelViewModel {
  arenaId: string;
  status: Exclude<ArenaPanelStatus, 'idle' | 'submitting'>;
  horizonRounds: number;
  committedRounds: number;
  completedRounds: number;
  manifest: ArenaPanelManifest;
  instances: ArenaPanelInstance[];
  rounds: ArenaPanelRound[];
  error?: { code: string; message: string; roundIndex?: number | null; instanceId?: string | null } | null;
}

export interface ArenaPanelProps {
  viewModel?: ArenaPanelViewModel | null;
  status?: ArenaPanelStatus;
  horizonRounds: number;
  error?: string | null;
  onHorizonChange: (horizonRounds: number) => void;
  onStart: (horizonRounds: number) => void;
  selectedRoundIndex?: number | null;
  onRoundChange?: (roundIndex: number) => void;
}

const instanceCount = 5;
const statusLabels: Record<ArenaPanelStatus, string> = {
  idle: 'Pronta para iniciar',
  submitting: 'Enviando solicitação',
  queued: 'Na fila',
  running: 'Em execução',
  succeeded: 'Concluída',
  failed: 'Falhou',
};
const formatNumber = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });
const routeExposureLabels = {
  exposed: 'há rota completa que passa por ao menos um nó alterado',
  not_exposed: 'nenhuma rota solicitada passa pelos nós alterados',
  unknown: 'não foi possível verificar a exposição das rotas',
} as const;
const formatMetric = (metric: ArenaPanelMetric) => metric.value === null
  ? `Indisponível — ${metric.nullReason || 'motivo não informado'}`
  : `${formatNumber.format(metric.value)} ${metric.unit}`;

function metricColumns(round: ArenaPanelRound | undefined) {
  const byId = new Map<string, ArenaPanelMetric>();
  round?.instances.forEach((instance) => instance.metrics.forEach((metric) => {
    if (!byId.has(metric.id)) byId.set(metric.id, metric);
  }));
  return [...byId.values()];
}

function cityStateCells(state: ArenaPanelCityState | null) {
  return {
    population: state?.population ? `${formatNumber.format(state.population.total)} residentes` : null,
    housing: state?.housing ? `${formatNumber.format(state.housing.totalUnits)} unidades` : null,
    jobs: state?.employment ? `${formatNumber.format(state.employment.totalJobs)} postos` : null,
    school: state?.services ? `${formatNumber.format(state.services.schoolDemand)} / ${formatNumber.format(state.services.schoolCapacity)}` : null,
    health: state?.services ? `${formatNumber.format(state.services.primaryHealthDemand)} / ${formatNumber.format(state.services.primaryHealthCapacity)}` : null,
    green: state?.publicGreenAreaM2 !== undefined ? `${formatNumber.format(state.publicGreenAreaM2)} m²` : null,
  };
}

export function ArenaPanel({
  viewModel,
  status = viewModel?.status ?? 'idle',
  horizonRounds,
  error,
  onHorizonChange,
  onStart,
  selectedRoundIndex,
  onRoundChange,
}: ArenaPanelProps) {
  const [localRoundIndex, setLocalRoundIndex] = useState<number | null>(null);
  const active = status === 'submitting' || status === 'queued' || status === 'running';
  const horizonValid = Number.isInteger(horizonRounds) && horizonRounds >= 1 && horizonRounds <= 10;
  const rounds = viewModel?.rounds ?? [];
  const chosenRoundIndex = selectedRoundIndex ?? localRoundIndex ?? rounds.at(-1)?.roundIndex ?? null;
  const selectedRound = rounds.find((round) => round.roundIndex === chosenRoundIndex);
  const selectedInstances = selectedRound?.instances ?? [];
  const columns = metricColumns(selectedRound);
  const errorMessage = error;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (horizonValid && !active) onStart(horizonRounds);
  };
  const selectRound = (roundIndex: number) => {
    setLocalRoundIndex(roundIndex);
    onRoundChange?.(roundIndex);
  };

  return (
    <section className="arena-panel" aria-labelledby="arena-panel-title">
      <header className="arena-panel-heading">
        <div>
          <p className="arena-eyebrow">SIMULAÇÃO ANUAL</p>
          <h2 id="arena-panel-title">Arena anual · Aurora sintética</h2>
          <p className="arena-panel-description">Os cinco participantes são políticas determinísticas de benchmark para temporização semafórica; não são agentes treinados nem tomam decisões autônomas. A comparação usa Aurora sintética. Cruzamento e janela aparecem na evidência de cada execução quando a resposta os identifica. Resultados sintéticos para exploração; sem ranking, vencedor ou score.</p>
        </div>
        <span className="arena-synthetic-label"><span aria-hidden="true">◇</span> AURORA SINTÉTICA</span>
      </header>

      <form className="arena-controls" onSubmit={submit}>
        <label htmlFor="arena-horizon">Horizonte anual</label>
        <select
          id="arena-horizon"
          value={horizonRounds}
          disabled={active}
          onChange={(event) => onHorizonChange(Number(event.currentTarget.value))}
        >
          {Array.from({ length: 10 }, (_, index) => index + 1).map((roundsCount) => (
            <option key={roundsCount} value={roundsCount}>{roundsCount} {roundsCount === 1 ? 'rodada' : 'rodadas'}</option>
          ))}
        </select>
        <button className="arena-start-button" type="submit" disabled={!horizonValid || active}>
          {status === 'submitting' ? 'Iniciando…' : viewModel ? 'Iniciar nova Arena' : 'Iniciar Arena'}
        </button>
      </form>

      <div className="arena-status-block" aria-live="polite">
        <div className="arena-status-line" role="status">
          <span className={`arena-status-dot arena-status-${status}`} aria-hidden="true" />
          <span>Estado: <strong>{statusLabels[status]}</strong></span>
          {viewModel && <code className="arena-id">{viewModel.arenaId}</code>}
        </div>
        {viewModel && <>
          <div className="arena-counts">
            <span><strong>{viewModel.completedRounds}</strong> de {viewModel.horizonRounds} rodadas publicadas</span>
            <span><strong>{viewModel.committedRounds}</strong> confirmadas pelo motor</span>
          </div>
          <progress className="arena-progress" max={viewModel.horizonRounds} value={viewModel.completedRounds} aria-label={`Rodadas publicadas: ${viewModel.completedRounds} de ${viewModel.horizonRounds}`} />
          {viewModel.committedRounds > viewModel.completedRounds && <p className="arena-partial-note">O motor confirmou estado, mas os detalhes de {viewModel.committedRounds - viewModel.completedRounds} {viewModel.committedRounds - viewModel.completedRounds === 1 ? 'rodada não foram publicados' : 'rodadas não foram publicados'}. Os hashes e índices confirmados seguem disponíveis abaixo.</p>}
        </>}
      </div>

      {errorMessage && <div className="arena-error" role="alert"><strong>Não foi possível concluir a solicitação.</strong><p>{errorMessage}</p></div>}

      {viewModel && <>
        <div className="arena-instance-section">
          <div className="arena-section-heading"><div><p className="arena-eyebrow">PARTICIPANTES</p><h3>Cinco políticas de referência</h3></div><span>{viewModel.instances.length} / {instanceCount}</span></div>
          <ul className="arena-instance-list">
            {viewModel.instances.map((instance, index) => <li key={instance.instanceId}>
              <span className="arena-instance-number" aria-hidden="true">0{index + 1}</span>
              <div className="arena-instance-copy"><strong>{instance.instanceId}</strong><span>{instance.policyId} · {instance.policyVersion} · índice confirmado {instance.currentRoundIndex}</span></div>
              {!instance.currentState && <span className="arena-state-unavailable">Detalhes indisponíveis</span>}
            </li>)}
          </ul>
        </div>

        {rounds.length > 0 && <div className="arena-round-section">
          <div className="arena-section-heading"><div><p className="arena-eyebrow">RESULTADOS PUBLICADOS</p><h3>Indicadores por rodada</h3></div><span>{rounds.length} {rounds.length === 1 ? 'rodada' : 'rodadas'}</span></div>
          <div className="arena-round-controls">
            <label htmlFor="arena-round">Rodada para inspecionar</label>
            <select id="arena-round" value={chosenRoundIndex ?? ''} onChange={(event) => selectRound(Number(event.currentTarget.value))}>
              {rounds.map((round) => <option key={round.roundIndex} value={round.roundIndex}>Rodada {round.roundIndex}</option>)}
            </select>
          </div>
          <p className="arena-table-note">Valores nulos permanecem indisponíveis e incluem o motivo informado. Os indicadores mostram unidade e período.</p>
          <div className="arena-table-scroll" tabIndex={0} aria-label="Tabela de instâncias e indicadores; role para navegar horizontalmente">
            <table>
              <caption>Estado urbano e indicadores das cinco instâncias na rodada {chosenRoundIndex}</caption>
              <thead><tr>
                <th scope="col">Instância</th><th scope="col">População</th><th scope="col">Habitação</th><th scope="col">Empregos</th>
                <th scope="col">Escolas<br /><small>demanda / capacidade</small></th><th scope="col">Saúde primária<br /><small>demanda / capacidade</small></th><th scope="col">Área verde pública</th>
                {columns.map((metric) => <th scope="col" key={metric.id}>{metric.label}<br /><small>{metric.unit} · {metric.period}</small></th>)}
              </tr></thead>
              <tbody>{viewModel.instances.map((instance) => {
                const result = selectedInstances.find((item) => item.instanceId === instance.instanceId);
                const state = instance.currentState?.roundIndex === chosenRoundIndex ? instance.currentState : null;
                const cells = cityStateCells(state);
                return <tr key={instance.instanceId}>
                  <th scope="row">{instance.instanceId}<small>{state ? `estado · rodada ${state.roundIndex}` : 'sem estado detalhado'}</small></th>
                  {([cells.population, cells.housing, cells.jobs, cells.school, cells.health, cells.green] as const).map((value, index) => <td key={index}>{value ?? <span className="arena-null">Indisponível — sem estado detalhado nesta rodada</span>}</td>)}
                  {columns.map((column) => {
                    const metric = result?.metrics.find((candidate) => candidate.id === column.id);
                    return <td key={column.id}>{metric ? <span className={metric.value === null ? 'arena-null' : undefined}>{formatMetric(metric)}{metric.unitBasis && <small className="arena-unit-basis">Base: {metric.unitBasis}</small>}</span> : '—'}</td>;
                  })}
                </tr>;
              })}</tbody>
            </table>
          </div>
          {selectedInstances.some((result) => result.actionExecutionEvidence) && <section className="arena-action-evidence" aria-labelledby="arena-action-evidence-title">
            <div className="arena-section-heading"><div><p className="arena-eyebrow">EVIDÊNCIA DE AÇÃO SEMAFÓRICA</p><h3 id="arena-action-evidence-title">Comparação SUMO por instância</h3></div></div>
            <p className="arena-evidence-note">Comparação SIMULADA e sintética entre baseline e intervenção em uma única janela. Não anualize estes resultados nem os misture com indicadores urbanos anuais.</p>
            {selectedInstances.filter((result) => result.actionExecutionEvidence).map((result) => {
              const evidence = result.actionExecutionEvidence!;
              const metrics = [
                ['Viagens solicitadas', 'trips_requested', 'viagens'], ['Viagens concluídas', 'trips_completed', 'viagens'],
                ['Viagens não concluídas', 'trips_not_completed', 'viagens'], ['Tempo médio de viagem', 'mean_travel_time_seconds', 's'],
                ['Velocidade média', 'mean_speed_kmh', 'km/h'], ['Fila média', 'mean_queue_length_meters', 'm'],
              ] as const;
              const policy = viewModel.instances.find((instance) => instance.instanceId === result.instanceId);
              return <article className="arena-evidence-card" key={result.instanceId} aria-label={`Evidência SUMO de ${result.instanceId}`}>
                <h4>{policy?.policyId ?? result.instanceId} <small>· {result.instanceId}</small></h4>
                <p className="arena-evidence-meta">Janela {evidence.windowId} · semente {evidence.seed} · {evidence.engine} {evidence.engineVersion}</p>
                <dl className="arena-evidence-scope"><div><dt>Cidade</dt><dd>Aurora sintética</dd></div><div><dt>Cruzamento</dt><dd>{result.signalTargetIds?.length ? result.signalTargetIds.join(', ') : 'não informado nesta resposta'}</dd></div><div><dt>Janela</dt><dd>{evidence.windowId}</dd></div></dl>
                <p className="arena-evidence-meta">Exposição das rotas: {routeExposureLabels[evidence.routeExposure]}</p>
                <p className="arena-evidence-actions">Ações: {evidence.actionIds.length ? evidence.actionIds.join(', ') : 'nenhuma ação identificada'}</p>
                <div className="arena-table-scroll" tabIndex={0} aria-label={`Métricas da comparação SUMO de ${result.instanceId}`}>
                  <table><caption>Baseline, intervenção e delta da janela {evidence.windowId} para {result.instanceId}</caption>
                    <thead><tr><th scope="col">Métrica</th><th scope="col">Baseline</th><th scope="col">Intervenção</th><th scope="col">Delta</th></tr></thead>
                    <tbody>{metrics.map(([label, key, unit]) => <tr key={key}><th scope="row">{label}</th>
                      {[evidence.baseMetrics, evidence.interventionMetrics, evidence.deltas].map((values, index) => <td key={index}>{values[key] === null ? 'Indisponível' : `${formatNumber.format(values[key]!)} ${unit}`}</td>)}
                    </tr>)}</tbody>
                  </table>
                </div>
                <dl className="arena-evidence-hashes"><div><dt>Snapshot</dt><dd>{evidence.snapshotId}</dd></div><div><dt>Hash do snapshot</dt><dd><code>{evidence.snapshotHash}</code></dd></div></dl>
                <ul className="arena-evidence-note">{evidence.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
              </article>;
            })}
          </section>}
          <details className="arena-round-details">
            <summary>Hashes e decisões confirmadas da rodada {chosenRoundIndex}</summary>
            <div className="arena-hash-list">{viewModel.instances.map((instance) => {
              const result = selectedInstances.find((item) => item.instanceId === instance.instanceId);
              const state = instance.currentState;
              return <dl key={instance.instanceId}>
                <div><dt>{instance.instanceId} · decisão</dt><dd>{result?.decision ?? 'detalhes não publicados'}</dd></div>
                <div><dt>Índice confirmado</dt><dd>{instance.currentRoundIndex}</dd></div>
                <div><dt>Hash do estado atual</dt><dd><code>{instance.currentCityStateHash}</code></dd></div>
                {state && <div><dt>Hash do estado selecionado</dt><dd><code>{state.cityStateHash}</code></dd></div>}
                {result && <><div><dt>Hash observado</dt><dd><code>{result.observedCityStateHash}</code></dd></div><div><dt>Hash do registro</dt><dd><code>{result.roundRecordHash}</code></dd></div><div><dt>Hash do manifesto na rodada</dt><dd><code>{result.manifestHash}</code></dd></div></>}
              </dl>;
            })}</div>
          </details>
        </div>}

        {viewModel.error && <p className="arena-error arena-job-error" role="alert"><strong>{viewModel.error.code}</strong> · {viewModel.error.message}{viewModel.error.roundIndex != null && ` (rodada ${viewModel.error.roundIndex})`}{viewModel.error.instanceId && ` · ${viewModel.error.instanceId}`}</p>}

        <details className="arena-manifest-details">
          <summary>Manifesto e hashes da execução</summary>
          <dl className="arena-manifest-grid">
            <div><dt>Snapshot</dt><dd>{viewModel.manifest.snapshotId}</dd></div><div><dt>Hash do snapshot</dt><dd><code>{viewModel.manifest.snapshotHash}</code></dd></div>
            <div><dt>Manifesto</dt><dd><code>{viewModel.manifest.hash}</code></dd></div><div><dt>Perfil de referência</dt><dd>{viewModel.manifest.profileId} · {viewModel.manifest.profileVersion}</dd></div>
            <div><dt>Versões</dt><dd>schema {viewModel.manifest.schemaVersion} · parâmetros {viewModel.manifest.parameterVersion}</dd></div>
            <div><dt>Motor</dt><dd>gerador {viewModel.manifest.generatorVersion} · transição {viewModel.manifest.transitionVersion}</dd></div>
            <div><dt>Catálogo / regras</dt><dd>{viewModel.manifest.catalogVersion} / {viewModel.manifest.rulesVersion}</dd></div><div><dt>Proveniência</dt><dd>{viewModel.manifest.provenance}</dd></div>
            <div><dt>Sementes</dt><dd><code>{JSON.stringify(viewModel.manifest.seeds)}</code></dd></div><div><dt>Parâmetros do manifesto</dt><dd><code>{JSON.stringify(viewModel.manifest.parameters)}</code></dd></div>
          </dl>
        </details>
      </>}
    </section>
  );
}

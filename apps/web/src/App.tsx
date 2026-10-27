import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchAurora, fetchComparison, fetchSimulation, startComparison, startSimulation, type Simulation, type SimulationComparison } from './api';
import type { CityData, LocalFeature } from './contracts';
import { MapView } from './MapView';
import { ArenaPanel, type ArenaPanelStatus } from './ArenaPanel';
import { fetchArena, startArena } from './arenaApi';
import { createArenaRequestSequence, isArenaPollingStatus, toArenaPanelViewModel } from './arenaViewModel';
import type { ArenaPanelViewModel } from './ArenaPanel';

type LoadState = 'loading' | 'ready' | 'error';
type LayerId = 'districts' | 'edges' | 'nodes';
const layerNames: Record<LayerId, string> = { districts: 'Distritos', edges: 'Vias', nodes: 'Cruzamentos' };

function displayValue(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return '—';
}

function valueFrom(feature: LocalFeature, candidates: string[]): unknown {
  const props = feature.properties ?? {};
  for (const key of candidates) if (props[key] !== undefined && props[key] !== null) return props[key];
  return undefined;
}

function FeatureTable({ data }: { data: CityData }) {
  const rows = useMemo(() => ([
    ...data.map.layers.districts.features.map((feature) => ({ layer: 'Distrito', feature })),
    ...data.map.layers.edges.features.map((feature) => ({ layer: 'Via', feature })),
    ...data.map.layers.nodes.features.map((feature) => ({ layer: 'Cruzamento', feature })),
  ]), [data]);
  return (
    <section className="table-section" aria-labelledby="table-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ALTERNATIVA ACESSÍVEL AO MAPA</p>
          <h2 id="table-title">Elementos de Aurora</h2>
        </div>
        <span className="row-count">{rows.length} elementos da API</span>
      </div>
      <div className="table-scroll" tabIndex={0} aria-label="Tabela de elementos, role para rolagem horizontal">
        <table>
          <caption>Distritos, vias e cruzamentos retornados pela API de Aurora</caption>
          <thead><tr><th scope="col">Camada</th><th scope="col">ID</th><th scope="col">Nome</th><th scope="col">Tipo</th><th scope="col">População</th><th scope="col">Empregos</th></tr></thead>
          <tbody>{rows.map(({ layer, feature }, index) => {
            const id = feature.id ?? valueFrom(feature, ['id', 'feature_id']);
            return <tr key={`${layer}-${String(id ?? index)}`}>
              <th scope="row">{layer}</th>
              <td>{displayValue(id)}</td>
              <td>{displayValue(valueFrom(feature, ['name', 'label', 'display_name']))}</td>
              <td>{displayValue(valueFrom(feature, ['type', 'kind', 'district_type']))}</td>
              <td>{displayValue(valueFrom(feature, ['population', 'residents', 'population_total']))}</td>
              <td>{displayValue(valueFrom(feature, ['jobs', 'employment', 'total_jobs']))}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <p className="table-note">Os valores mostram somente propriedades fornecidas pela API. Traços indicam campos não fornecidos.</p>
    </section>
  );
}

function LoadingState() {
  return <div className="status-card" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" /><div><h2>Carregando Aurora</h2><p>Buscando metadados e geometria na API…</p></div></div>;
}

function SimulationPanel() {
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [windowId, setWindowId] = useState('weekday_am_peak');

  useEffect(() => {
    if (!simulation || !['queued', 'running'].includes(simulation.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      fetchSimulation(simulation.simulation_id, controller.signal).then((updated) => {
        if (!controller.signal.aborted) setSimulation(updated);
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : 'Não foi possível consultar a execução.');
          setSimulation(null);
          controller.abort();
        }
      });
    }, 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [simulation?.simulation_id, simulation?.status]);

  const begin = async () => {
    setSimulation(null);
    setError('');
    setSending(true);
    try { setSimulation(await startSimulation(windowId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Não foi possível iniciar a simulação.'); }
    finally { setSending(false); }
  };

  const active = simulation && ['queued', 'running'].includes(simulation.status);
  const statusText: Record<Simulation['status'], string> = {
    queued: 'Na fila', running: 'Em execução', succeeded: 'Concluída', failed: 'Falhou', cancelled: 'Cancelada',
  };
  const metrics = simulation?.status === 'succeeded' ? simulation.metrics : null;
  return <section className="simulation-panel" aria-labelledby="simulation-title">
    <div className="section-heading">
      <div><p className="eyebrow">EXECUÇÃO REPRODUZÍVEL · SEMENTE 42</p><h2 id="simulation-title">Simulação-base</h2></div>
      <span className="synthetic-pill">AURORA SINTÉTICA</span>
    </div>
    <p className="simulation-description">Inicia uma execução para a janela selecionada. Após a última partida, o escoamento pode continuar por até 3.600 s para permitir que os veículos solicitados terminem; esse período pode ultrapassar a janela de demanda. Os resultados são de um benchmark sintético e não representam medições nem validação de uma cidade real.</p>
    <div className="simulation-controls">
      <label htmlFor="simulation-window">Janela disponível</label>
      <select id="simulation-window" value={windowId} disabled={sending || Boolean(active)} onChange={(event) => setWindowId(event.target.value)}>
        <option value="weekday_am_peak">Pico da manhã (weekday_am_peak)</option><option value="weekday_off_peak">Fora de pico (weekday_off_peak)</option>
      </select>
      <button className="primary-button" type="button" disabled={sending || Boolean(active)} onClick={begin}>
        {sending ? 'Enviando…' : simulation?.status === 'failed' || error ? 'Tentar novamente' : 'Executar simulação-base'}
      </button>
    </div>
    {sending && <p className="simulation-live" role="status" aria-live="polite">Enviando solicitação à API…</p>}
    {error && <div className="simulation-error" role="alert"><strong>Não foi possível acompanhar a simulação.</strong><p>{error}</p></div>}
    {simulation && <div className="simulation-result" aria-live="polite">
      <div className="simulation-state" role="status"><span className={`state-dot state-${simulation.status}`} />Estado: <strong>{statusText[simulation.status]}</strong></div>
      <dl className="snapshot-details simulation-details">
        <div><dt>Execução</dt><dd>{simulation.simulation_id}</dd></div><div><dt>Snapshot</dt><dd>{simulation.snapshot_id}</dd></div>
        <div><dt>Semente</dt><dd>{simulation.seed}</dd></div><div><dt>Motor</dt><dd>{simulation.engine_version}</dd></div>
      </dl>
      {simulation.status === 'failed' && <p role="alert" className="simulation-error">{simulation.error?.message || 'A execução falhou. Tente novamente.'}</p>}
      {simulation.status === 'cancelled' && <p className="simulation-live">A execução foi cancelada; nenhum resultado foi publicado.</p>}
      {metrics && <>
        <h3>Métricas retornadas pela API</h3>
        <dl className="result-metrics">
          <div><dt>Viagens solicitadas</dt><dd>{metrics.trips_requested} <small>viagens</small></dd></div>
          <div><dt>Viagens concluídas</dt><dd>{metrics.trips_completed} <small>viagens</small></dd></div>
          <div><dt>Viagens não concluídas</dt><dd>{metrics.trips_not_completed} <small>viagens pendentes</small></dd></div>
          <div><dt>Tempo médio de viagem</dt><dd>{metrics.mean_travel_time_seconds ?? '—'} <small>segundos</small></dd></div>
          <div><dt>Velocidade média</dt><dd>{metrics.mean_speed_kmh ?? '—'} <small>km/h</small></dd></div>
          <div><dt>Fila média</dt><dd>{metrics.mean_queue_length_meters ?? '—'} <small>metros</small></dd></div>
        </dl>
      </>}
      {simulation.warnings.length > 0 && <div className="simulation-warnings"><strong>Avisos da execução</strong><ul>{simulation.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul></div>}
    </div>}
  </section>;
}

const comparisonMetrics: { key: keyof NonNullable<SimulationComparison['base_metrics']>; label: string; unit: string }[] = [
  { key: 'trips_requested', label: 'Viagens solicitadas', unit: 'viagens' },
  { key: 'trips_completed', label: 'Viagens concluídas', unit: 'viagens' },
  { key: 'trips_not_completed', label: 'Viagens não concluídas', unit: 'viagens' },
  { key: 'mean_travel_time_seconds', label: 'Tempo médio de viagem', unit: 's' },
  { key: 'mean_speed_kmh', label: 'Velocidade média', unit: 'km/h' },
  { key: 'mean_queue_length_meters', label: 'Fila média', unit: 'm' },
];

function formatComparisonValue(value: number | null | undefined, signed = false): string {
  if (value === null || value === undefined) return '—';
  const formatted = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value);
  return signed && value > 0 ? `+${formatted}` : formatted;
}

function ScenarioComparisonPanel() {
  const [comparison, setComparison] = useState<SimulationComparison | null>(null);
  const [windowId, setWindowId] = useState('weekday_am_peak');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!comparison || !['queued', 'running'].includes(comparison.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      fetchComparison(comparison.comparison_id, controller.signal).then((updated) => {
        if (!controller.signal.aborted) setComparison(updated);
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : 'Não foi possível consultar a comparação.');
          setComparison(null);
          controller.abort();
        }
      });
    }, 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [comparison?.comparison_id, comparison?.status]);

  const begin = async () => {
    setComparison(null);
    setError('');
    setSending(true);
    try { setComparison(await startComparison(windowId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Não foi possível iniciar a comparação.'); }
    finally { setSending(false); }
  };

  const active = comparison && ['queued', 'running'].includes(comparison.status);
  const statusNames: Record<SimulationComparison['status'], string> = {
    queued: 'Na fila', running: 'Em execução', succeeded: 'Concluída', failed: 'Falhou',
  };

  return <section className="simulation-panel comparison-panel" aria-labelledby="comparison-title">
    <div className="section-heading">
      <div><p className="eyebrow">EXPERIMENTO PAREADO · MESMA SEMENTE E DEMANDA</p><h2 id="comparison-title">Base versus temporização semafórica</h2></div>
      <span className="synthetic-pill">AURORA SINTÉTICA</span>
    </div>
    <p className="simulation-description">Executa a base e uma intervenção declarativa somente em <code>node:02:04</code>: norte-sul 40 s, todos vermelhos 3 s, leste-oeste 20 s, todos vermelhos 3 s. O ciclo permanece em 66 s. Rotas do pico da manhã alcançam este cruzamento. Ambas as execuções usam a mesma rede, demanda, semente e escoamento de até 3.600 s. Benchmark sintético, sem validação empírica.</p>
    <div className="simulation-controls">
      <label htmlFor="comparison-window">Janela de demanda</label>
      <select id="comparison-window" value={windowId} disabled={sending || Boolean(active)} onChange={(event) => setWindowId(event.target.value)}>
        <option value="weekday_am_peak">Pico da manhã (weekday_am_peak)</option><option value="weekday_off_peak">Fora de pico (weekday_off_peak)</option>
      </select>
      <button className="primary-button" type="button" disabled={sending || Boolean(active)} onClick={begin}>
        {sending ? 'Enviando…' : 'Executar comparação pareada'}
      </button>
    </div>
    {sending && <p className="simulation-live" role="status">Enviando comparação à API…</p>}
    {error && <div className="simulation-error" role="alert"><strong>Não foi possível acompanhar a comparação.</strong><p>{error}</p></div>}
    {comparison && <div className="simulation-result" aria-live="polite">
      <div className="simulation-state" role="status"><span className={`state-dot state-${comparison.status}`} />Estado: <strong>{statusNames[comparison.status]}</strong></div>
      <dl className="snapshot-details simulation-details">
        <div><dt>Comparação</dt><dd>{comparison.comparison_id}</dd></div>
        <div><dt>Snapshot comum</dt><dd>{comparison.common_parameters.snapshot_id}</dd></div>
        <div><dt>Janela</dt><dd>{comparison.common_parameters.window_id}</dd></div>
        <div><dt>Semente</dt><dd>{comparison.common_parameters.seed}</dd></div>
        <div><dt>Escoamento</dt><dd>{comparison.common_parameters.drain_limit_seconds} s</dd></div>
        <div><dt>Demanda pareada</dt><dd>{comparison.common_parameters.trips_requested} viagens · {comparison.common_parameters.demand_hash.slice(0, 12)}</dd></div>
      </dl>
      {comparison.route_exposure && <p className="simulation-live">Exposição das rotas: {comparison.route_exposure === 'exposed' ? 'confirmada — ao menos uma rota válida alcança o cruzamento' : comparison.route_exposure === 'not_exposed' ? 'nenhuma rota válida alcança o cruzamento' : 'não verificável — arquivo de rotas ausente, inválido ou incompleto'}.</p>}
      {comparison.status === 'failed' && <p role="alert" className="simulation-error">{comparison.error?.scenario ? `Falha no cenário ${comparison.error.scenario === 'base' ? 'base' : 'de intervenção'}: ` : ''}{comparison.error?.message || 'Uma das simulações falhou; a comparação não publicou métricas parciais.'}</p>}
      {comparison.status === 'succeeded' && comparison.base_metrics && comparison.intervention_metrics && comparison.deltas && <>
        <p className="table-note">Delta = intervenção − base. Valores nulos permanecem indisponíveis.</p>
        <div className="table-scroll comparison-table-scroll" tabIndex={0} aria-label="Métricas pareadas, role para rolagem horizontal">
          <table className="comparison-table">
            <caption>Métricas lado a lado e diferenças entre os dois resultados SUMO</caption>
            <thead><tr><th scope="col">Indicador</th><th scope="col">Base</th><th scope="col">Intervenção</th><th scope="col">Delta</th></tr></thead>
            <tbody>{comparisonMetrics.map(({ key, label, unit }) => <tr key={key}>
              <th scope="row">{label} <small>({unit})</small></th>
              <td>{formatComparisonValue(comparison.base_metrics?.[key])}</td>
              <td>{formatComparisonValue(comparison.intervention_metrics?.[key])}</td>
              <td>{formatComparisonValue(comparison.deltas?.[key], true)}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="comparison-identities">
          <p><strong>Base</strong> · execução {comparison.base_result?.simulation_id} · SUMO {comparison.base_result?.engine_version}</p>
          <p><strong>Intervenção</strong> · execução {comparison.intervention_result?.simulation_id} · SUMO {comparison.intervention_result?.engine_version}</p>
        </div>
      </>}
      {(comparison.base_warnings.length > 0 || comparison.intervention_warnings.length > 0) && <div className="simulation-warnings">
        <strong>Avisos por cenário</strong>
        {comparison.base_warnings.length > 0 && <div><b>Base</b><ul>{comparison.base_warnings.map((warning, index) => <li key={`base-${index}`}>{warning}</li>)}</ul></div>}
        {comparison.intervention_warnings.length > 0 && <div><b>Intervenção</b><ul>{comparison.intervention_warnings.map((warning, index) => <li key={`intervention-${index}`}>{warning}</li>)}</ul></div>}
      </div>}
    </div>}
  </section>;
}

function AnnualArenaPanel() {
  const [horizonRounds, setHorizonRounds] = useState(10);
  const [viewModel, setViewModel] = useState<ArenaPanelViewModel | null>(null);
  const [status, setStatus] = useState<ArenaPanelStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const sequence = useRef<ReturnType<typeof createArenaRequestSequence> | null>(null);
  if (!sequence.current) sequence.current = createArenaRequestSequence();

  useEffect(() => () => { sequence.current?.invalidate(); }, []);

  useEffect(() => {
    if (!viewModel || !isArenaPollingStatus(viewModel.status) || !sequence.current?.isCurrent(generation)) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const job = await fetchArena(viewModel.arenaId);
        if (stopped || !sequence.current?.isCurrent(generation)) return;
        const updated = toArenaPanelViewModel(job);
        setViewModel(updated);
        setStatus(updated.status);
        setError(null);
        if (isArenaPollingStatus(updated.status)) timer = window.setTimeout(poll, 1500);
      } catch (reason) {
        if (stopped || !sequence.current?.isCurrent(generation)) return;
        setError(reason instanceof Error ? reason.message : 'Não foi possível consultar a Arena.');
        setStatus('failed');
      }
    };
    timer = window.setTimeout(poll, 1500);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [generation, viewModel?.arenaId, viewModel?.status]);

  const begin = async (horizon: number) => {
    const requestGeneration = sequence.current!.begin();
    setGeneration(requestGeneration);
    setViewModel(null);
    setError(null);
    setStatus('submitting');
    try {
      const job = await startArena(horizon);
      if (!sequence.current!.isCurrent(requestGeneration)) return;
      const mapped = toArenaPanelViewModel(job);
      setViewModel(mapped);
      setStatus(mapped.status);
    } catch (reason) {
      if (!sequence.current!.isCurrent(requestGeneration)) return;
      setError(reason instanceof Error ? reason.message : 'Não foi possível iniciar a Arena.');
      setStatus('failed');
    }
  };

  return <ArenaPanel
    viewModel={viewModel}
    status={status}
    horizonRounds={horizonRounds}
    error={error}
    onHorizonChange={setHorizonRounds}
    onStart={begin}
  />;
}

export default function App() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>('loading');
  const [data, setData] = useState<CityData | null>(null);
  const [error, setError] = useState('');
  const [visible, setVisible] = useState<Record<LayerId, boolean>>({ districts: true, edges: true, nodes: true });

  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    setData(null);
    setError('');
    fetchAurora(controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      setData(result);
      setState('ready');
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setData(null);
      setError(reason instanceof Error ? reason.message : 'Não foi possível carregar Aurora.');
      setState('error');
    });
    return () => controller.abort();
  }, [attempt]);

  const toggle = (id: LayerId) => setVisible((current) => ({ ...current, [id]: !current[id] }));

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#inicio" aria-label="Urban Twin Arena, início">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <span>URBAN TWIN <b>ARENA</b></span>
        </a>
        <div className="topbar-meta"><span className="live-dot" /> MVP 0 <span className="topbar-divider">/</span> VISUALIZAÇÃO</div>
      </header>

      <div className="content" id="inicio">
        <div className="page-intro">
          <div>
            <p className="eyebrow">BENCHMARK URBANO · VERSÃO 0.1</p>
            <h1>Uma cidade. Um ponto de partida.</h1>
            <p className="intro-copy">Explore o esquema territorial de Aurora, a cidade-base sintética da Urban Twin Arena.</p>
          </div>
          <div className="synthetic-stamp"><span aria-hidden="true">◇</span> SINTÉTICO</div>
        </div>

        {state === 'loading' && <LoadingState />}
        {state === 'error' && <section className="status-card error-card" role="alert">
          <div className="error-icon" aria-hidden="true">!</div>
          <div className="error-content"><p className="eyebrow">FALHA AO CARREGAR</p><h2>Não foi possível abrir Aurora</h2><p>{error}</p>
            <button className="primary-button" type="button" onClick={() => setAttempt((value) => value + 1)}>Tentar novamente <span aria-hidden="true">↻</span></button>
          </div>
        </section>}

        {state === 'ready' && data && <>
          <section className="workspace" aria-label="Visão geral de Aurora">
            <div className="map-column"><MapView cityMap={data.map} visible={visible} />
              <div className="legend-panel" aria-label="Legenda e controles de camadas">
                <div className="legend-title"><span className="eyebrow">CAMADAS DO MAPA</span><span className="local-tag">LOCAL · m</span></div>
                <div className="layer-controls">
                  <label className="layer-option"><input type="checkbox" checked={visible.districts} onChange={() => toggle('districts')} /><span className="legend-shape district-shape" aria-hidden="true" />{layerNames.districts}</label>
                  <label className="layer-option"><input type="checkbox" checked={visible.edges} onChange={() => toggle('edges')} /><span className="legend-shape edge-shape" aria-hidden="true" />{layerNames.edges}</label>
                  <label className="layer-option"><input type="checkbox" checked={visible.nodes} onChange={() => toggle('nodes')} /><span className="legend-shape node-shape" aria-hidden="true" />{layerNames.nodes}</label>
                </div>
              </div>
            </div>
            <aside className="city-panel" aria-labelledby="city-title">
              <div className="city-panel-top"><p className="eyebrow">CIDADE-BASE</p><span className="synthetic-pill"><span aria-hidden="true">◇</span> SINTÉTICO</span></div>
              <h2 id="city-title">{data.metadata.name}<span className="city-period">.</span></h2>
              <p className="city-id">{data.metadata.city_id}</p>
              <p className="snapshot-hash"><span>HASH DO SNAPSHOT</span><code title={data.metadata.hash}>{data.metadata.hash}</code></p>
              <div className="metric-stack">
                <div className="metric"><span>População</span><strong>{new Intl.NumberFormat('pt-BR').format(data.metadata.population.total)}</strong><small>residentes</small></div>
                <div className="metric"><span>Empregos</span><strong>{new Intl.NumberFormat('pt-BR').format(data.metadata.jobs)}</strong><small>postos sintéticos</small></div>
              </div>
              <div className="provenance-note"><span aria-hidden="true">ⓘ</span><p>Aurora é um esquema sintético local para desenvolvimento e benchmark. Não representa uma cidade real nem possui localização geográfica.</p></div>
              <dl className="snapshot-details"><div><dt>Snapshot</dt><dd>{data.metadata.snapshot_id}</dd></div><div><dt>Proveniência</dt><dd>{data.metadata.provenance}</dd></div></dl>
            </aside>
          </section>
          <AnnualArenaPanel />
          <SimulationPanel />
          <ScenarioComparisonPanel />
          <FeatureTable data={data} />
          <footer className="page-footer"><span>URBAN TWIN ARENA <b>·</b> AURORA SINTÉTICA</span><span>Geometria fornecida pela API · espaço cartesiano local</span></footer>
        </>}
      </div>
    </main>
  );
}

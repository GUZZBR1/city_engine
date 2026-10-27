import { useEffect, useMemo, useState } from 'react';
import { fetchAurora, fetchSimulation, fetchTrafficCompetition, startSimulation, startTrafficCompetition, type Simulation, type TrafficCompetition } from './api';
import type { CityData, LocalFeature } from './contracts';
import { MapView } from './MapView';

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
          <h2 id="table-title">Elementos da rede viária</h2>
        </div>
        <span className="row-count">{rows.length} elementos da API</span>
      </div>
      <div className="table-scroll" tabIndex={0} aria-label="Tabela de elementos, role para rolagem horizontal">
        <table>
          <caption>Áreas, vias e cruzamentos retornados pela API de Aurora</caption>
          <thead><tr><th scope="col">Camada</th><th scope="col">ID</th><th scope="col">Nome</th><th scope="col">Tipo</th><th scope="col">Velocidade</th><th scope="col">Faixas</th><th scope="col">Capacidade</th></tr></thead>
          <tbody>{rows.map(({ layer, feature }, index) => {
            const id = feature.id ?? valueFrom(feature, ['id', 'feature_id']);
            return <tr key={`${layer}-${String(id ?? index)}`}>
              <th scope="row">{layer}</th>
              <td>{displayValue(id)}</td>
              <td>{displayValue(valueFrom(feature, ['name', 'label', 'display_name']))}</td>
              <td>{displayValue(valueFrom(feature, ['type', 'kind', 'district_type']))}</td>
              <td>{displayValue(valueFrom(feature, ['speed_limit_kmh']))}{valueFrom(feature, ['speed_limit_kmh']) !== undefined ? ' km/h' : ''}</td>
              <td>{displayValue(valueFrom(feature, ['lanes']))}</td>
              <td>{displayValue(valueFrom(feature, ['capacity_vehicles_per_hour']))}{valueFrom(feature, ['capacity_vehicles_per_hour']) !== undefined ? ' veíc./h' : ''}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <p className="table-note">Velocidade, faixas e capacidade são hipóteses sintéticas por trecho, fornecidas pela API; traços indicam campos não aplicáveis ou não fornecidos.</p>
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

function formatComparisonValue(value: number | null | undefined, signed = false): string {
  if (value === null || value === undefined) return '—';
  const formatted = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value);
  return signed && value > 0 ? `+${formatted}` : formatted;
}

function TrafficCompetitionPanel() {
  const [competition, setCompetition] = useState<TrafficCompetition | null>(null);
  const [windowId, setWindowId] = useState('weekday_am_peak');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!competition || !['queued', 'running'].includes(competition.status)) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      fetchTrafficCompetition(competition.competition_id, controller.signal).then((updated) => {
        if (!controller.signal.aborted) setCompetition(updated);
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : 'Não foi possível consultar a competição.');
          setCompetition(null);
          controller.abort();
        }
      });
    }, 1500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [competition?.competition_id, competition?.status]);

  const begin = async () => {
    setCompetition(null);
    setError('');
    setSending(true);
    try { setCompetition(await startTrafficCompetition(windowId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Não foi possível iniciar a competição.'); }
    finally { setSending(false); }
  };

  const active = competition && ['queued', 'running'].includes(competition.status);
  const statusNames: Record<TrafficCompetition['status'], string> = {
    queued: 'Na fila', running: 'Em execução', succeeded: 'Concluída', failed: 'Falhou',
  };

  return <section className="simulation-panel comparison-panel" aria-labelledby="competition-title">
    <div className="section-heading">
      <div><p className="eyebrow">SEIS EXECUÇÕES PAREADAS · UMA BASE + CINCO EMPRESAS</p><h2 id="competition-title">Competição de operação viária</h2></div>
      <span className="synthetic-pill">AURORA SINTÉTICA</span>
    </div>
    <p className="simulation-description">Cada empresa aplica uma estratégia diferente de temporização no cruzamento <code>node:02:04</code>. As cinco usam a mesma rede, demanda, semente e ciclo semafórico de 66 s, comparadas com a mesma execução-base. Esta primeira competição testa operação semafórica; obras, pavimentação e rodovias entram quando o modelo viário as suportar.</p>
    <div className="simulation-controls">
      <label htmlFor="competition-window">Janela de demanda</label>
      <select id="competition-window" value={windowId} disabled={sending || Boolean(active)} onChange={(event) => setWindowId(event.target.value)}>
        <option value="weekday_am_peak">Pico da manhã (weekday_am_peak)</option><option value="weekday_off_peak">Fora de pico (weekday_off_peak)</option>
      </select>
      <button className="primary-button" type="button" disabled={sending || Boolean(active)} onClick={begin}>
        {sending ? 'Enviando…' : 'Executar competição de empresas'}
      </button>
    </div>
    {sending && <p className="simulation-live" role="status">Preparando cinco estratégias na API…</p>}
    {error && <div className="simulation-error" role="alert"><strong>Não foi possível acompanhar a competição.</strong><p>{error}</p></div>}
    {competition && <div className="simulation-result" aria-live="polite">
      <div className="simulation-state" role="status"><span className={`state-dot state-${competition.status}`} />Estado: <strong>{statusNames[competition.status]}</strong></div>
      <dl className="snapshot-details simulation-details">
        <div><dt>Competição</dt><dd>{competition.competition_id}</dd></div>
        <div><dt>Snapshot comum</dt><dd>{competition.common_parameters.snapshot_id}</dd></div>
        <div><dt>Janela</dt><dd>{competition.common_parameters.window_id}</dd></div>
        <div><dt>Semente</dt><dd>{competition.common_parameters.seed}</dd></div>
        <div><dt>Escoamento</dt><dd>{competition.common_parameters.drain_limit_seconds} s</dd></div>
        <div><dt>Demanda pareada</dt><dd>{competition.common_parameters.trips_requested} viagens · {competition.common_parameters.demand_hash.slice(0, 12)}</dd></div>
      </dl>
      <div className="company-roster" aria-label="Empresas e políticas participantes">
        {competition.companies.map((company) => <article key={company.company_id}>
          <strong>{company.name}</strong>
          <span>{company.strategy}</span>
          <small>Fases do ciclo: {company.intervention.phases.map((phase) => phase.duration_seconds).join(' · ')} s</small>
        </article>)}
      </div>
      {competition.status === 'failed' && <p role="alert" className="simulation-error">{competition.error?.company_id ? `Falha em ${competition.error.company_id}: ` : ''}{competition.error?.message || 'Uma execução falhou; a competição não publicou resultados parciais.'}</p>}
      {competition.status === 'succeeded' && competition.baseline_metrics && <>
        <p className="table-note">Delta = estratégia da empresa − base. As métricas permanecem separadas; nenhum peso ou vencedor geral é presumido.</p>
        <div className="table-scroll comparison-table-scroll" tabIndex={0} aria-label="Resultados das cinco empresas, role para rolagem horizontal">
          <table className="comparison-table company-results-table">
            <caption>Resultados pareados das cinco empresas contra a execução-base</caption>
            <thead><tr><th scope="col">Empresa e estratégia</th><th scope="col">Viagens concluídas</th><th scope="col">Tempo médio</th><th scope="col">Velocidade média</th><th scope="col">Fila média</th></tr></thead>
            <tbody>
              <tr className="baseline-row">
                <th scope="row"><strong>Execução-base</strong><small>Referência comum às cinco empresas</small></th>
                <td>{formatComparisonValue(competition.baseline_metrics.trips_completed)} <small>(referência)</small></td>
                <td>{formatComparisonValue(competition.baseline_metrics.mean_travel_time_seconds)} s <small>(referência)</small></td>
                <td>{formatComparisonValue(competition.baseline_metrics.mean_speed_kmh)} km/h <small>(referência)</small></td>
                <td>{formatComparisonValue(competition.baseline_metrics.mean_queue_length_meters)} m <small>(referência)</small></td>
              </tr>
              {competition.companies.map((company) => <tr key={company.company_id}>
              <th scope="row"><strong>{company.name}</strong><small>{company.strategy}</small></th>
              <td>{formatComparisonValue(company.metrics?.trips_completed)} <small>({formatComparisonValue(company.deltas_vs_baseline?.trips_completed, true)})</small></td>
              <td>{formatComparisonValue(company.metrics?.mean_travel_time_seconds)} s <small>({formatComparisonValue(company.deltas_vs_baseline?.mean_travel_time_seconds, true)} s)</small></td>
              <td>{formatComparisonValue(company.metrics?.mean_speed_kmh)} km/h <small>({formatComparisonValue(company.deltas_vs_baseline?.mean_speed_kmh, true)})</small></td>
              <td>{formatComparisonValue(company.metrics?.mean_queue_length_meters)} m <small>({formatComparisonValue(company.deltas_vs_baseline?.mean_queue_length_meters, true)} m)</small></td>
              </tr>)}
            </tbody>
          </table>
        </div>
        <p className="comparison-identities"><strong>Referência-base</strong> · execução {competition.baseline_result?.simulation_id} · SUMO {competition.baseline_result?.engine_version}</p>
        {competition.companies.some((company) => company.warnings.length > 0 || company.route_exposure !== 'exposed') && <div className="simulation-warnings">
          <strong>Avisos das estratégias</strong>
          {competition.companies.filter((company) => company.warnings.length > 0 || company.route_exposure !== 'exposed').map((company) => <div key={company.company_id}>
            <b>{company.name}</b><ul>{company.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </div>)}
        </div>}
      </>}
    </div>}
  </section>;
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
        <div className="topbar-meta"><span className="live-dot" /> ARENA DE TRÁFEGO <span className="topbar-divider">/</span> COMPETIÇÃO PAREADA</div>
      </header>

      <div className="content" id="inicio">
        <div className="page-intro">
          <div>
            <p className="eyebrow">ARENA DE TRÁFEGO · VERSÃO 0.1</p>
            <h1>Cinco empresas. Uma rede viária.</h1>
            <p className="intro-copy">Empresas de infraestrutura disputam estratégias para ruas, estradas e rodovias sob a mesma demanda e as mesmas regras.</p>
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
          <section className="focus-banner" aria-label="Escopo da arena">
            <strong>Foco atual: tráfego e infraestrutura viária</strong>
            <p>A competição executa cinco políticas de operação semafórica contra a mesma rede e a mesma execução-base. Esta primeira rodada cobre um cruzamento; obras, pavimentação e rodovias serão incluídas conforme o modelo viário crescer.</p>
          </section>
          <section className="workspace" aria-label="Visão geral da rede viária de Aurora">
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
              <div className="city-panel-top"><p className="eyebrow">REDE VIÁRIA-BASE</p><span className="synthetic-pill"><span aria-hidden="true">◇</span> SINTÉTICA</span></div>
              <h2 id="city-title">{data.metadata.name}<span className="city-period">.</span></h2>
              <p className="city-id">{data.metadata.city_id}</p>
              <p className="snapshot-hash"><span>HASH DO SNAPSHOT</span><code title={data.metadata.hash}>{data.metadata.hash}</code></p>
              <div className="metric-stack">
                <div className="metric"><span>Trechos direcionados</span><strong>{new Intl.NumberFormat('pt-BR').format(data.map.layers.edges.features.length)}</strong><small>arestas viárias</small></div>
                <div className="metric"><span>Cruzamentos</span><strong>{new Intl.NumberFormat('pt-BR').format(data.map.layers.nodes.features.length)}</strong><small>nós da rede</small></div>
              </div>
              <div className="provenance-note"><span aria-hidden="true">ⓘ</span><p>Aurora é uma rede viária sintética para desenvolvimento e benchmark. Não representa uma cidade real nem possui localização geográfica.</p></div>
              <dl className="snapshot-details"><div><dt>Snapshot</dt><dd>{data.metadata.snapshot_id}</dd></div><div><dt>Proveniência</dt><dd>{data.metadata.provenance}</dd></div></dl>
            </aside>
          </section>
          <SimulationPanel />
          <TrafficCompetitionPanel />
          <FeatureTable data={data} />
          <footer className="page-footer"><span>URBAN TWIN ARENA <b>·</b> FOCO EM TRÁFEGO</span><span>Geometria viária sintética · espaço cartesiano local</span></footer>
        </>}
      </div>
    </main>
  );
}

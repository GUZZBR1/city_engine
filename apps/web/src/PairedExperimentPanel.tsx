import { useEffect, useMemo, useState } from 'react';
import { createPairedExperiment, fetchPairedExperiment, pairOutcome, type CreateExperimentInput, type DeltaValue, type ExpectedExperimentPlan, type MetricValue, type PairedExperiment } from './pairedExperiment';
import './PairedExperimentPanel.css';

const windowOptions = [
  { id: 'weekday_am_peak', label: 'Pico da manhã' },
  { id: 'weekday_off_peak', label: 'Fora de pico' },
];
const statusLabel: Record<PairedExperiment['status'], string> = { queued: 'Na fila', running: 'Em execução', succeeded: 'Completo', partial: 'Parcial · incompleto', failed: 'Falhou', cancelled: 'Cancelado' };
const executionLabel = { queued: 'Na fila', running: 'Em execução', succeeded: 'Concluída', failed: 'Falhou', cancelled: 'Cancelada' } as const;
const metricLabels: Record<string, string> = { trips_requested: 'Viagens solicitadas', trips_completed: 'Viagens concluídas', trips_not_completed: 'Viagens não concluídas', mean_travel_time_seconds: 'Tempo médio de viagem', mean_speed_kmh: 'Velocidade média', mean_queue_length_meters: 'Fila média' };
const metricOptions = Object.keys(metricLabels);

function parseIntegerList(raw: string, label: string, allowEmpty = false): number[] {
  const values = raw.split(',').map((item) => item.trim()).filter(Boolean);
  if (!values.length && allowEmpty) return [];
  if (!values.length || values.some((item) => !/^\d+$/.test(item))) throw new Error(`${label}: informe inteiros separados por vírgula.`);
  const numbers = values.map(Number);
  if (numbers.some((item) => !Number.isSafeInteger(item) || item < 0)) throw new Error(`${label}: use inteiros não negativos.`);
  if (new Set(numbers).size !== numbers.length) throw new Error(`${label}: não repita valores.`);
  return numbers.sort((a, b) => a - b);
}

function format(value: number | null | undefined, signed = false): string {
  if (value === null || value === undefined) return 'Não disponível';
  const result = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value);
  return signed && value > 0 ? `+${result}` : result;
}
function metricLabel(id: string) { return metricLabels[id] ?? id; }
function statusClass(status: string) { return `paired-status paired-${status}`; }
function pairOutcomeLabel(outcome: ReturnType<typeof pairOutcome>) { return { completed: 'Par completo', running: 'Em execução', failed: 'Inválido', missing: 'Sem resultado completo' }[outcome]; }

export function MetricProvenanceCell({ baseline, strategy, delta }: { baseline?: MetricValue; strategy?: MetricValue; delta?: DeltaValue }) {
  const armSource = (value?: MetricValue) => value ? <>{value.provenance_kind} · {value.period} · {value.method_version}<br /><code>SHA-256 {value.artifact_sha256}</code></> : 'Não disponível';
  return <td><div className="paired-provenance"><div><strong>Baseline:</strong> {armSource(baseline)}</div><div><strong>Estratégia:</strong> {armSource(strategy)}</div><div><strong>Delta:</strong> {delta ? `${delta.provenance_kind} · ${delta.method_version} · ${delta.direction}` : 'Não disponível'}</div></div></td>;
}

function ExperimentCreateForm({ onCreated }: { onCreated: (experiment: PairedExperiment, input: CreateExperimentInput) => void }) {
  const [windows, setWindows] = useState<string[]>([]);
  const [seeds, setSeeds] = useState('');
  const [strategyIds, setStrategyIds] = useState('');
  const [baseline, setBaseline] = useState('');
  const [arenaManifestId, setArenaManifestId] = useState('');
  const [arenaManifestHash, setArenaManifestHash] = useState('');
  const [roundIndex, setRoundIndex] = useState(1);
  const [instanceId, setInstanceId] = useState('');
  const [primaryMetrics, setPrimaryMetrics] = useState<string[]>([]);
  const [secondaryMetrics, setSecondaryMetrics] = useState<string[]>([]);
  const [drainLimit, setDrainLimit] = useState('');
  const [method, setMethod] = useState('explicit_list_user_supplied');
  const [masterSeed, setMasterSeed] = useState('');
  const [maxAttempts, setMaxAttempts] = useState('');
  const [reproChecks, setReproChecks] = useState('');
  const [wallPerRun, setWallPerRun] = useState('');
  const [wallTotal, setWallTotal] = useState('');
  const [maxRuns, setMaxRuns] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const seedCount = useMemo(() => { try { return parseIntegerList(seeds, 'Seeds').length; } catch { return 0; } }, [seeds]);
  const strategyCount = strategyIds.split(',').map((value) => value.trim()).filter(Boolean).length;
  const pairCount = windows.length * strategyCount * seedCount;
  const maxCalls = pairCount * 2 * (Number(maxAttempts) || 0) + (Number(reproChecks) || 0);
  const maxWallUpper = maxCalls * (Number(wallPerRun) || 0);
  const budgetReady = maxRuns !== '' && maxAttempts !== '' && reproChecks !== '' && wallPerRun !== '' && wallTotal !== '' && drainLimit !== '' && Number.isSafeInteger(Number(maxRuns)) && Number(maxRuns) > 0 && Number.isSafeInteger(Number(maxAttempts)) && Number(maxAttempts) > 0 && Number.isSafeInteger(Number(reproChecks)) && Number(reproChecks) >= 0 && Number.isSafeInteger(Number(wallPerRun)) && Number(wallPerRun) > 0 && Number.isSafeInteger(Number(wallTotal)) && Number(wallTotal) > 0 && Number.isSafeInteger(Number(drainLimit)) && Number(drainLimit) > 0;

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    let seedValues: number[];
    try {
      seedValues = parseIntegerList(seeds, 'Seeds');
      if (!windows.length) throw new Error('Selecione ao menos uma janela configurada.');
      const strategies = strategyIds.split(',').map((value) => value.trim()).filter(Boolean);
      if (!strategies.length || new Set(strategies).size !== strategies.length) throw new Error('Informe estratégias sem duplicatas.');
      if (strategies.includes(baseline)) throw new Error('A estratégia baseline não deve ser incluída na lista de braços.');
      if (!budgetReady) throw new Error('Preencha os limites de execuções, tentativas, tempo e escoamento com inteiros válidos.');
      if (maxCalls > Number(maxRuns)) throw new Error(`O limite de ${maxRuns} execuções é menor que o teto do plano (${maxCalls}).`);
      if (!arenaManifestId.trim() || !/^[a-f0-9]{64}$/.test(arenaManifestHash)) throw new Error('Informe a identidade e o hash SHA-256 do manifesto imutável da Arena.');
      if (!instanceId.trim()) throw new Error('Informe a instância da Arena associada ao experimento.');
      if (!primaryMetrics.length) throw new Error('Selecione ao menos uma métrica primária antes de iniciar.');
      if (primaryMetrics.some((metric) => secondaryMetrics.includes(metric))) throw new Error('Uma métrica não pode ser primária e secundária ao mesmo tempo.');
      if ([...primaryMetrics, ...secondaryMetrics].some((metric) => ['mean_travel_time_seconds', 'mean_speed_kmh'].includes(metric)) && ['trips_requested', 'trips_completed', 'trips_not_completed'].some((metric) => !primaryMetrics.includes(metric) && !secondaryMetrics.includes(metric))) throw new Error('Métricas de tempo ou velocidade exigem viagens solicitadas, concluídas e não concluídas no plano.');
      if (maxWallUpper > Number(wallTotal)) throw new Error(`O tempo total máximo de ${wallTotal} s não cobre o teto conservador do plano (${maxWallUpper} s).`);
      const input: CreateExperimentInput = {
        arena_manifest_id: arenaManifestId.trim(), arena_manifest_sha256: arenaManifestHash,
        round_index: roundIndex, instance_id: instanceId.trim(),
        window_ids: [...windows].sort(), strategy_ids: strategies.sort(), baseline_strategy_id: baseline,
        seeds: seedValues, seed_scope: 'sumo_operational_randomness', seed_selection_method: method,
        master_seed: masterSeed.trim() ? Number(masterSeed) : null, primary_metric_ids: [...primaryMetrics].sort(),
        secondary_metric_ids: [...secondaryMetrics].sort(), drain_limit_seconds: Number(drainLimit),
        max_sumo_runs: Number(maxRuns), max_attempts_per_execution: Number(maxAttempts),
        max_reproducibility_checks: Number(reproChecks), max_wall_clock_seconds_per_run: Number(wallPerRun),
        max_total_wall_clock_seconds: Number(wallTotal),
      };
      if (input.master_seed !== null && (!Number.isSafeInteger(input.master_seed) || input.master_seed < 0)) throw new Error('A seed mestre deve ser um inteiro não negativo.');
      setBusy(true);
      onCreated(await createPairedExperiment(input), input);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Não foi possível criar o experimento.');
    } finally { setBusy(false); }
  };

  return <form className="paired-create" onSubmit={submit} aria-labelledby="paired-create-title">
    <div className="paired-subheading"><div><p className="eyebrow">PLANO IMUTÁVEL · DEFINA ANTES DE EXECUTAR</p><h3 id="paired-create-title">Novo experimento pareado</h3></div><span className="protocol-tag">AURORA · V1</span></div>
    <fieldset className="window-selection">
      <legend>Janelas configuradas <span>(selecione explicitamente)</span></legend>
      <div className="paired-window-options">{windowOptions.map((item) => <label className="paired-choice" key={item.id}>
        <input type="checkbox" checked={windows.includes(item.id)} disabled={busy} onChange={() => setWindows((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />
        <span><strong>{item.label}</strong><small>{item.id}</small></span>
      </label>)}</div>
    </fieldset>
    <div className="paired-form-grid">
      <label>ID do manifesto imutável da Arena<input value={arenaManifestId} disabled={busy} onChange={(event) => setArenaManifestId(event.target.value)} required /></label>
      <label>SHA-256 do manifesto da Arena<input value={arenaManifestHash} disabled={busy} onChange={(event) => setArenaManifestHash(event.target.value)} pattern="[a-f0-9]{64}" required /></label>
      <label>Rodada da Arena<input type="number" min="1" step="1" value={roundIndex} disabled={busy} onChange={(event) => setRoundIndex(Number(event.target.value))} /></label>
      <label>ID da instância da Arena<input value={instanceId} disabled={busy} onChange={(event) => setInstanceId(event.target.value)} required /></label>
      <label>Seeds SUMO <span className="field-hint">Inteiros explícitos, separados por vírgula</span><input value={seeds} disabled={busy} onChange={(event) => setSeeds(event.target.value)} aria-describedby="paired-seed-note" /></label>
      <label>Método de seleção das seeds<input value={method} disabled={busy} onChange={(event) => setMethod(event.target.value)} required /></label>
      <label>Estratégias <span className="field-hint">IDs separados por vírgula</span><input value={strategyIds} disabled={busy} onChange={(event) => setStrategyIds(event.target.value)} required /></label>
      <label>ID do baseline<input value={baseline} disabled={busy} onChange={(event) => setBaseline(event.target.value)} required /></label>
      <label>Seed mestre <span className="field-hint">Opcional; não é seed de demanda</span><input inputMode="numeric" value={masterSeed} disabled={busy} onChange={(event) => setMasterSeed(event.target.value)} placeholder="Não aplicável" /></label>
      <label>Máximo de execuções SUMO<input type="number" min="1" step="1" value={maxRuns} disabled={busy} onChange={(event) => setMaxRuns(event.target.value)} required /></label>
      <label>Limite de escoamento (s)<input type="number" min="1" step="1" value={drainLimit} disabled={busy} onChange={(event) => setDrainLimit(event.target.value)} required /></label>
      <label>Tentativas máximas por execução<input type="number" min="1" step="1" value={maxAttempts} disabled={busy} onChange={(event) => setMaxAttempts(event.target.value)} required /></label>
      <label>Verificações de reprodutibilidade<input type="number" min="0" step="1" value={reproChecks} disabled={busy} onChange={(event) => setReproChecks(event.target.value)} required /></label>
      <label>Tempo máximo por execução (s)<input type="number" min="1" step="1" value={wallPerRun} disabled={busy} onChange={(event) => setWallPerRun(event.target.value)} required /></label>
      <label>Tempo total máximo (s)<input type="number" min="1" step="1" value={wallTotal} disabled={busy} onChange={(event) => setWallTotal(event.target.value)} required /></label>
    </div>
    <fieldset className="window-selection metric-selection"><legend>Métricas do estudo <span>(fixe antes da execução)</span></legend>
      <div className="paired-metric-groups">{(['primary', 'secondary'] as const).map((kind) => <div key={kind}><h4>{kind === 'primary' ? 'Primárias' : 'Secundárias'}</h4>{metricOptions.map((metric) => <label key={`${kind}-${metric}`}><input type="checkbox" checked={(kind === 'primary' ? primaryMetrics : secondaryMetrics).includes(metric)} disabled={busy} onChange={() => {
        const setter = kind === 'primary' ? setPrimaryMetrics : setSecondaryMetrics;
        setter((current) => current.includes(metric) ? current.filter((id) => id !== metric) : [...current, metric]);
      }} />{metricLabel(metric)}</label>)}</div>)}</div>
    </fieldset>
    <p className="paired-plan-count" id="paired-seed-note"><strong>{pairCount}</strong> pares planejados · até <strong>{maxCalls}</strong> chamadas SUMO · teto conservador de <strong>{new Intl.NumberFormat('pt-BR').format(maxWallUpper)} s</strong>. Sementes repetidas são rejeitadas.</p>
    <p className="paired-adapter-note">O servidor deve vincular este plano à configuração imutável da Arena, às políticas e à demanda expandida e retornar o DTO v1.0 validado.</p>
    {error && <div className="paired-error" role="alert">{error}</div>}
    <button className="primary-button" disabled={busy || pairCount === 0 || !budgetReady} type="submit">{busy ? 'Criando manifesto…' : 'Criar experimento'}</button>
  </form>;
}

function SummaryTable({ experiment }: { experiment: PairedExperiment }) {
  return <section className="paired-results" aria-labelledby="paired-summary-title">
    <div className="paired-section-heading"><div><p className="eyebrow">RESUMOS SEGREGADOS POR JANELA</p><h3 id="paired-summary-title">Distribuição e incerteza</h3></div><p>Os ICs são marginais e condicionais à aleatoriedade operacional do SUMO.</p></div>
    {experiment.summaries_by_window.length === 0 ? <p className="paired-empty">Sem resumos disponíveis para as janelas planejadas.</p> : <><p className="paired-note">O DTO v1.0 documenta um único campo <code>arm_summary</code> e não especifica se ele resume baseline ou estratégia. A tabela preserva esse campo sem atribuí-lo a um braço.</p><div className="paired-table-scroll" tabIndex={0} aria-label="Resumos por janela, estratégia e métrica; use as setas ou rolagem para navegar">
      <table><caption>Resumo por janela, estratégia e métrica. Cada linha permanece separada por janela.</caption><thead><tr><th scope="col">Janela</th><th scope="col">Estratégia</th><th scope="col">Métrica</th><th scope="col">Período</th><th scope="col">n completo / planejado</th><th scope="col">Braços: média · DP · mediana · IIQ · mín–máx</th><th scope="col">Δ pareado: média · DP · mediana · IIQ · mín–máx</th><th scope="col">IC t 95% da média Δ</th><th scope="col">Método / proveniência</th></tr></thead>
        <tbody>{experiment.summaries_by_window.map((item, index) => <tr key={`${item.window_id}-${item.strategy_id}-${item.metric_id}-${index}`}>
          <th scope="row">{item.window_id}</th><td>{item.strategy_id}</td><td>{metricLabel(item.metric_id)} <small>({item.unit})</small></td><td>{item.period === 'demand_window' ? 'Janela de demanda' : 'Viagens concluídas até o escoamento'}</td><td>{item.n_complete} / {item.n_planned}</td><td>{format(item.arm_summary.mean)} · {format(item.arm_summary.sd)} · {format(item.arm_summary.median)} · {format(item.arm_summary.iqr)} · {format(item.arm_summary.min)}–{format(item.arm_summary.max)}</td><td>{format(item.paired_delta_summary.mean, true)} · {format(item.paired_delta_summary.sd)} · {format(item.paired_delta_summary.median, true)} · {format(item.paired_delta_summary.iqr)} · {format(item.paired_delta_summary.min, true)}–{format(item.paired_delta_summary.max, true)}</td><td>{experiment.status !== 'succeeded' || item.n_complete !== item.n_planned || item.confidence_interval.n !== item.n_planned ? 'Não inferir · conjunto incompleto' : item.confidence_interval.n < 2 ? 'Indisponível · n < 2' : `${format(item.confidence_interval.lower, true)} a ${format(item.confidence_interval.upper, true)} (n=${item.confidence_interval.n}, gl=${item.confidence_interval.degrees_of_freedom})`}</td><td>{item.confidence_interval.method} · {item.provenance_kind} · {item.method_version}</td>
        </tr>)}</tbody>
      </table>
    </div></>}
  </section>;
}

const PAGE_SIZE = 100;
function PairList({ experiment }: { experiment: PairedExperiment }) {
  const [shown, setShown] = useState(PAGE_SIZE);
  useEffect(() => setShown(PAGE_SIZE), [experiment.experiment_id]);
  const visiblePairs = experiment.pairs.slice(0, shown);
  const statusCount = experiment.pairs.length;
  const unlistedCount = Math.max(0, experiment.planned_pairs - statusCount);
  return <section className="paired-results" aria-labelledby="paired-pairs-title">
    <div className="paired-section-heading"><div><p className="eyebrow">REGISTROS INDIVIDUAIS</p><h3 id="paired-pairs-title">Pares por janela e seed</h3></div><p>{statusCount} pares detalhados neste DTO · {unlistedCount} combinações planejadas sem linha detalhada · {experiment.missing_pairs} pares faltantes segundo o contador da API</p></div>
    <p className="paired-note">Cada par reúne baseline e estratégia com entradas comuns identificadas por hash. `route_exposure` indica somente passagem de rota pela área alterada; não identifica veículos afetados. A API v1.0 não documenta os eixos selecionados nem como serializa cada par ausente; linhas ausentes não podem ser enumeradas sem inventar uma identidade.</p>
    {experiment.pairs.length === 0 ? <p className="paired-empty">O DTO não contém linhas de pares. A ausência permanece explícita; contadores planejados não são convertidos em resultados.</p> : <div className="paired-pair-list">
      {visiblePairs.map((pair, index) => <details className="paired-pair" key={`${pair.pair_id}-${index}`}>
        <summary><span className={statusClass(`state-${pairOutcome(pair)}`)}>{pairOutcomeLabel(pairOutcome(pair))}</span><strong>{pair.window_id}</strong><span>Seed {pair.seed}</span><span>{pair.strategy_id}</span><code>{pair.pair_id}</code><span>Rotas: {pair.route_exposure === 'unknown' ? 'desconhecido' : pair.route_exposure === 'exposed' ? 'cruzam a área' : 'sem cruzamento identificado'}</span></summary>
        <div className="paired-pair-content"><dl className="paired-identities"><div><dt>Estado retornado</dt><dd>{pair.status}</dd></div><div><dt>Estado derivado dos braços e delta</dt><dd>{pairOutcomeLabel(pairOutcome(pair))}</dd></div><div><dt>Pair ID</dt><dd>{pair.pair_id}</dd></div><div><dt>Hash de entrada comum</dt><dd>{pair.common_input_sha256}</dd></div><div><dt>Execução baseline</dt><dd>{pair.baseline_execution_id} · {executionLabel[pair.executions.baseline.status]}</dd></div><div><dt>Execução estratégia</dt><dd>{pair.strategy_execution_id} · {executionLabel[pair.executions.strategy.status]}</dd></div></dl>
          <div className="paired-arm-grid">{(['baseline', 'strategy'] as const).map((arm) => <div key={arm}><h4>{arm === 'baseline' ? 'Baseline' : `Estratégia · ${pair.strategy_id}`}</h4><p>{pair.executions[arm].attempts.length} tentativas</p><ul>{pair.executions[arm].attempts.map((attempt, i) => <li key={`${attempt.attempt}-${i}`}>Tentativa {attempt.attempt} · {executionLabel[attempt.status]}{attempt.error ? ` · ${attempt.error}` : ''}{attempt.artifact_sha256 ? ` · artefato ${attempt.artifact_sha256.slice(0, 12)}…` : ''}</li>)}</ul></div>)}</div>
          {(pair.baseline_metrics || pair.strategy_metrics || pair.deltas) && <div className="paired-values"><h4>{pairOutcome(pair) === 'completed' ? 'Valores e deltas (estratégia − baseline)' : 'Resultados do braço concluído · sem delta pareado'}</h4><div className="paired-table-scroll" tabIndex={0} aria-label={`Métricas do par ${pair.pair_id}`}><table><caption>Métricas disponíveis por braço; deltas somente para pares completos</caption><thead><tr><th scope="col">Métrica</th><th scope="col">Baseline</th><th scope="col">Estratégia</th><th scope="col">Delta</th><th scope="col">Proveniência por valor</th></tr></thead><tbody>{Array.from(new Set([...Object.keys(pair.baseline_metrics ?? {}), ...Object.keys(pair.strategy_metrics ?? {}), ...Object.keys(pair.deltas ?? {})])).map((id) => {
            const base = pair.baseline_metrics?.[id]; const strategy = pair.strategy_metrics?.[id]; const delta = pair.deltas?.[id];
            return <tr key={id}><th scope="row">{metricLabel(id)}</th><td>{base ? format(base.value) : 'Métrica não disponível'}</td><td>{strategy ? format(strategy.value) : 'Métrica não disponível'}</td><td>{delta ? format(delta.value, true) : 'Métrica não disponível'}</td><MetricProvenanceCell baseline={base} strategy={strategy} delta={delta} /></tr>;
          })}</tbody></table></div></div>}
          {pairOutcome(pair) !== 'completed' && <p className="paired-missing">Par sem resultado válido completo. As métricas indisponíveis não são mostradas como zero.</p>}
        </div>
      </details>)}
      {experiment.pairs.length > shown && <button className="quiet-button paired-more" type="button" onClick={() => setShown((current) => Math.min(experiment.pairs.length, current + PAGE_SIZE))}>Mostrar mais {Math.min(PAGE_SIZE, experiment.pairs.length - shown)} pares ({shown} de {experiment.pairs.length})</button>}
    </div>}
  </section>;
}

function ExperimentDetails({ experiment, onRetry }: { experiment: PairedExperiment; onRetry: () => void }) {
  const active = experiment.status === 'queued' || experiment.status === 'running';
  return <div className="paired-experiment-result">
    <div className="paired-overview"><div><p className="eyebrow">EXPERIMENTO · {experiment.dto_schema_version} / PROTOCOLO {experiment.protocol_version}</p><h3>{experiment.experiment_id}</h3></div><span className={statusClass(experiment.status)} role="status">{statusLabel[experiment.status]}</span></div>
    <div className="paired-counts" aria-label="Contagem de pares"><div><strong>{experiment.planned_pairs}</strong><span>Planejados</span></div><div><strong>{experiment.completed_pairs}</strong><span>Completos</span></div><div><strong>{experiment.failed_pairs}</strong><span>Falhos</span></div><div><strong>{experiment.running_pairs}</strong><span>Em execução</span></div><div><strong>{experiment.missing_pairs}</strong><span>Faltantes</span></div></div>
    <p className="paired-sr-only" aria-live="polite">Estado {statusLabel[experiment.status]}. Planejados {experiment.planned_pairs}; completos {experiment.completed_pairs}; falhos {experiment.failed_pairs}; em execução {experiment.running_pairs}; faltantes {experiment.missing_pairs}.</p>
    {experiment.status === 'partial' && <div className="paired-missing" role="status"><strong>Resultado parcial e incompleto.</strong> Os resumos são apenas descritivos de pares completos, sujeitos à seleção por falhas. IC inferencial está oculto nesta apresentação.</div>}
    {active && <p className="paired-live" role="status" aria-live="polite">Atualizando o experimento automaticamente…</p>}
    <dl className="paired-manifest"><div><dt>Manifesto do experimento</dt><dd>{experiment.manifest_sha256}</dd></div><div><dt>Manifesto da Arena referenciado</dt><dd>{experiment.arena_manifest_id} · {experiment.arena_manifest_sha256}</dd></div></dl>
    <SummaryTable experiment={experiment} />
    <PairList experiment={experiment} />
    <section className="paired-caveats" aria-labelledby="paired-limitations-title"><h3 id="paired-limitations-title">Escopo e limites de interpretação</h3><ul>{experiment.limitations.map((item) => <li key={item}>{item.replaceAll('_', ' ')}</li>)}</ul><p>Aurora, a rede, a demanda e as intervenções são sintéticas. Resultados SUMO cobrem somente a janela e o escoamento configurado; filas agregam a rede e tempo/velocidade cobrem viagens concluídas até o fim do escoamento. Não há efeito isolado nos veículos expostos. Resultados não são anualizados e não sustentam inferência sobre tráfego real nem alegação causal. `route_exposure` indica passagem de uma rota pela área alterada; não segmenta resultados nem identifica veículos afetados.</p></section>
    {experiment.status === 'partial' || experiment.status === 'failed' ? <button className="quiet-button" type="button" onClick={onRetry}>Atualizar estado</button> : null}
  </div>;
}

export function PairedExperimentPanel() {
  const [experiment, setExperiment] = useState<PairedExperiment | null>(null);
  const [expectedPlan, setExpectedPlan] = useState<ExpectedExperimentPlan | null>(null);
  const [lookupId, setLookupId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [failedLookupId, setFailedLookupId] = useState('');
  const active = experiment?.status === 'queued' || experiment?.status === 'running';

  useEffect(() => {
    if (!active || !experiment) return;
    const controller = new AbortController();
    let timer: number;
    const poll = async () => {
      try {
        const updated = await fetchPairedExperiment(experiment.experiment_id, controller.signal, expectedPlan ?? undefined);
        if (controller.signal.aborted) return;
        setExperiment(updated);
        setError('');
        if (updated.status === 'queued' || updated.status === 'running') timer = window.setTimeout(poll, 1500);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : 'Não foi possível atualizar o experimento.');
          timer = window.setTimeout(poll, 3000);
        }
      }
    };
    timer = window.setTimeout(poll, 1500);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [active, experiment?.experiment_id, experiment?.status, expectedPlan]);

  const lookup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError(''); setFailedLookupId(lookupId.trim());
    const plan = experiment?.experiment_id === lookupId.trim() ? expectedPlan : null;
    setExpectedPlan(plan);
    try { const loaded = await fetchPairedExperiment(lookupId.trim(), undefined, plan ?? undefined); setExperiment(loaded); setFailedLookupId(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Não foi possível carregar o experimento.'); }
    finally { setBusy(false); }
  };
  const retry = () => {
    const id = failedLookupId || experiment?.experiment_id;
    if (!id) return;
    setLookupId(id); setError('');
    const plan = experiment?.experiment_id === id ? expectedPlan : null;
    setExpectedPlan(plan);
    void fetchPairedExperiment(id, undefined, plan ?? undefined).then((loaded) => { setExperiment(loaded); setFailedLookupId(''); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Falha ao tentar novamente.'));
  };

  return <section className="simulation-panel paired-panel" aria-labelledby="paired-experiment-title">
    <div className="section-heading"><div><p className="eyebrow">PROTOCOLO DE EXPERIMENTO PAREADO · MULTI-SEED</p><h2 id="paired-experiment-title">Experimento SUMO por janela</h2></div><span className="synthetic-pill">AURORA SINTÉTICA</span></div>
    <p className="simulation-description">Compare cada estratégia com o mesmo baseline, snapshot, demanda expandida, janela e seed. Seeds variam somente a aleatoriedade operacional do SUMO; não amostram demanda. Resumos e incerteza permanecem separados por janela.</p>
    <ExperimentCreateForm onCreated={(created, input) => { setExperiment(created); setExpectedPlan({ window_ids: input.window_ids, strategy_ids: input.strategy_ids, seeds: input.seeds, primary_metric_ids: input.primary_metric_ids, secondary_metric_ids: input.secondary_metric_ids }); setLookupId(created.experiment_id); setFailedLookupId(''); setError(''); }} />
    <form className="paired-lookup" onSubmit={lookup}><label htmlFor="paired-lookup-id">Acompanhar experimento existente</label><input id="paired-lookup-id" value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder="experiment_id" required /><button className="quiet-button" disabled={busy} type="submit">{busy ? 'Carregando…' : 'Carregar'}</button></form>
    {error && <div className="paired-error" role="alert"><strong>Não foi possível carregar ou atualizar o experimento.</strong><p>{error}</p><button className="quiet-button" type="button" disabled={busy} onClick={retry}>Tentar novamente</button></div>}
    {experiment && <ExperimentDetails experiment={experiment} onRetry={retry} />}
  </section>;
}

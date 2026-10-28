import { useEffect, useRef, useState } from 'react';
import { cancelAndRefreshPairedExperiment, createPairedExperiment, computePolicySha256, fetchPairedExperiment, isCurrentExperimentRequest, pairOutcome, rememberCancellationAcknowledgement, retryPairedExperiment, shouldSelectCreatedExperiment, type CreateExperimentInput, type DeltaValue, type ExpectedExperimentPlan, type MetricValue, type PairedExperiment, type MultiSeedBudget, type StrategyInput } from './pairedExperiment';
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

export function MetricProvenanceCell({ baseline, strategy, delta, rawBaseline, rawStrategy }: { baseline?: MetricValue; strategy?: MetricValue; delta?: DeltaValue; rawBaseline?: { method: string; artifact: string | null }; rawStrategy?: { method: string; artifact: string | null } }) {
  const armSource = (value?: MetricValue, raw?: { method: string; artifact: string | null }) => value ? <>{value.provenance_kind} · {value.period} · {value.method_version}<br /><code>SHA-256 {value.artifact_sha256}</code></> : raw ? <>result_metrics bruto · {raw.method}<br /><code>SHA-256 {raw.artifact ?? 'não disponível'}</code></> : 'Não disponível';
  return <td><div className="paired-provenance"><div><strong>Baseline:</strong> {armSource(baseline, rawBaseline)}</div><div><strong>Estratégia:</strong> {armSource(strategy, rawStrategy)}</div><div><strong>Delta:</strong> {delta ? <>{delta.provenance_kind} · {delta.method_version} · {delta.direction}<br/><code>SHA-256 {delta.source_artifact_sha256.join(' / ')}</code></> : 'Não disponível'}</div></div></td>;
}

function ExperimentCreateForm({ onCreateStarted, onCreated }: { onCreateStarted: () => number; onCreated: (experiment: PairedExperiment, input: CreateExperimentInput, generation: number) => void }) {
  const [windows, setWindows] = useState<string[]>([]), [seeds, setSeeds] = useState('42, 43, 44');
  const [arenaId,setArenaId]=useState(''),[arenaHash,setArenaHash]=useState(''),[round,setRound]=useState('1'),[instance,setInstance]=useState('');
  const [strategies,setStrategies]=useState('[]');
  const [baseline,setBaseline]=useState(''),[baselineVersion,setBaselineVersion]=useState('1');
  const [metrics,setMetrics]=useState<string[]>(['trips_requested','trips_completed','trips_not_completed']),[primary,setPrimary]=useState<string[]>(['trips_completed']);
  const [tolerances,setTolerances]=useState('{"trips_requested":{"exact":true},"trips_completed":{"exact":true},"trips_not_completed":{"exact":true}}');
  const [drain,setDrain]=useState('0'),[runs,setRuns]=useState('24'),[attempts,setAttempts]=useState('1'),[wallRun,setWallRun]=useState('3600'),[wallTotal,setWallTotal]=useState('86400'),[admitIncomplete,setAdmitIncomplete]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''); const pairCount=windows.length*parseIntegerListSafe(seeds).length*parseStrategyCount(strategies); const requiredRuns=pairCount*2*(Number(attempts)||0); const requiredWall=requiredRuns*(Number(wallRun)||0);
  const toggle=(items:string[],set:(v:string[])=>void,id:string)=>set(items.includes(id)?items.filter(x=>x!==id):[...items,id]);
  const submit=async(e:React.FormEvent<HTMLFormElement>)=>{e.preventDefault();setError('');try{
    const seedList=parseIntegerList(seeds,'Seeds'); if(!windows.length)throw Error('Selecione ao menos uma janela configurada.');
    const strategyDrafts=JSON.parse(strategies) as Array<Omit<StrategyInput,'policy_sha256'> & {policy_sha256?:string}>; if(!Array.isArray(strategyDrafts)||!strategyDrafts.length)throw Error('Informe a lista de estratégias no formato JSON da API.'); const strategyList:StrategyInput[]=await Promise.all(strategyDrafts.map(async strategy=>({...strategy,policy_sha256:await computePolicySha256(strategy.strategy_id,strategy.policy_version,strategy.intervention)}))); const baselineHash=await computePolicySha256(baseline,baselineVersion,null);
    const budget:MultiSeedBudget={max_sumo_runs:Number(runs),max_attempts_per_execution:Number(attempts),max_reproducibility_checks:0,max_wall_clock_seconds_per_run:Number(wallRun),max_total_wall_clock_seconds:Number(wallTotal),admit_incomplete:admitIncomplete};
    if(![budget.max_sumo_runs,budget.max_attempts_per_execution,budget.max_wall_clock_seconds_per_run,budget.max_total_wall_clock_seconds].every(Number.isFinite)||budget.max_sumo_runs<1||budget.max_attempts_per_execution<1||budget.max_wall_clock_seconds_per_run<=0||budget.max_wall_clock_seconds_per_run>3600||budget.max_total_wall_clock_seconds<=0)throw Error('Revise os limites de orçamento da API.');
    if(!admitIncomplete&&(Number(runs)<requiredRuns||Number(wallTotal)<requiredWall))throw Error(`Orçamento insuficiente: o plano requer até ${requiredRuns} execuções e ${requiredWall}s.`); const metricTolerances=JSON.parse(tolerances) as CreateExperimentInput['metric_tolerances']; if(!primary.length||primary.some(m=>!metrics.includes(m)))throw Error('Métricas primárias devem ser subconjunto das métricas solicitadas.');
    if(metrics.some(m=>['mean_travel_time_seconds','mean_speed_kmh'].includes(m))&&['trips_requested','trips_completed','trips_not_completed'].some(m=>!metrics.includes(m)))throw Error('Tempo/velocidade exigem as três métricas de contagem de viagens.');
    const input:CreateExperimentInput={arena_manifest_id:arenaId,arena_manifest_sha256:arenaHash,round_index:Number(round),instance_id:instance,city_id:'aurora-base-v1',window_ids:[...windows],seeds:seedList,strategies:strategyList,baseline_id:baseline,baseline_version:baselineVersion,baseline_sha256:baselineHash,drain_limit_seconds:Number(drain),metrics,metric_tolerances:metricTolerances,method_version:'sumo-metrics-v1',budget,reproducibility_checks:0,selection_method:'externally_predeclared',master_seed:null,primary_metrics:primary,confidence_level:0.95};
    const generation=onCreateStarted();setBusy(true);onCreated(await createPairedExperiment(input),input,generation);
  }catch(err){setError(err instanceof Error?err.message:'Não foi possível criar o experimento.');}finally{setBusy(false);}};
  return <form className="paired-create" onSubmit={submit} aria-labelledby="paired-create-title"><div className="paired-subheading"><div><p className="eyebrow">PLANO IMUTÁVEL · DEFINA ANTES DE EXECUTAR</p><h3 id="paired-create-title">Novo experimento pareado</h3></div><span className="protocol-tag">AURORA · V1</span></div>
    <fieldset className="window-selection"><legend>Janelas configuradas <span>(selecione explicitamente)</span></legend><div className="paired-window-options">{windowOptions.map(w=><label className="paired-choice" key={w.id}><input type="checkbox" checked={windows.includes(w.id)} disabled={busy} onChange={()=>toggle(windows,setWindows,w.id)}/><span><strong>{w.label}</strong><small>{w.id}</small></span></label>)}</div></fieldset>
    <div className="paired-form-grid"><label>ID do manifesto imutável da Arena<input value={arenaId} onChange={e=>setArenaId(e.target.value)} required/></label><label>SHA-256 do manifesto da Arena<input value={arenaHash} onChange={e=>setArenaHash(e.target.value)} pattern="[a-f0-9]{64}" required/></label><label>Rodada<input type="number" min="0" value={round} onChange={e=>setRound(e.target.value)} required/></label><label>Instância<input value={instance} onChange={e=>setInstance(e.target.value)} required/></label><label>Seeds SUMO<input value={seeds} onChange={e=>setSeeds(e.target.value)} aria-describedby="paired-seed-note" required/><span className="field-hint">Lista explícita; varia aleatoriedade operacional, não demanda.</span></label><label>ID baseline<input value={baseline} onChange={e=>setBaseline(e.target.value)} required/></label><label>Versão baseline<input value={baselineVersion} onChange={e=>setBaselineVersion(e.target.value)} required/></label><p className="field-hint">O hash JCS do baseline sem intervenção é calculado ao enviar.</p><label>Limite de drain (s)<input type="number" min="0" max="604800" value={drain} onChange={e=>setDrain(e.target.value)} required/></label><label>Máximo de execuções SUMO<input type="number" min="1" value={runs} onChange={e=>setRuns(e.target.value)} required/></label><label>Tentativas por execução<input type="number" min="1" value={attempts} onChange={e=>setAttempts(e.target.value)} required/></label><label>Tempo por execução (s)<input type="number" min="1" max="3600" value={wallRun} onChange={e=>setWallRun(e.target.value)} required/></label><label>Orçamento total (s)<input type="number" min="1" value={wallTotal} onChange={e=>setWallTotal(e.target.value)} required/></label></div>
    <label>Estratégias (JSON: strategy_id, policy_version e intervention; hash JCS calculado ao enviar)<textarea rows={8} value={strategies} onChange={e=>setStrategies(e.target.value)} required/></label>
    <fieldset className="window-selection metric-selection"><legend>Métricas solicitadas e primárias</legend><div className="paired-metric-groups">{metricOptions.map(m=><div key={m}><label><input type="checkbox" checked={metrics.includes(m)} onChange={()=>toggle(metrics,setMetrics,m)}/>{metricLabel(m)}</label>{metrics.includes(m)&&<label><input type="checkbox" checked={primary.includes(m)} onChange={()=>toggle(primary,setPrimary,m)}/>Primária</label>}</div>)}</div></fieldset>
    <label>Tolerâncias pré-declaradas (JSON da API)<textarea rows={4} value={tolerances} onChange={e=>setTolerances(e.target.value)} required/><span className="field-hint">Cada métrica precisa de exact=true ou valores absolute e relative.</span></label>
    <label><input type="checkbox" checked={admitIncomplete} onChange={e=>setAdmitIncomplete(e.target.checked)}/> Admitir plano incompleto se exceder limites do servidor</label>
    <p className="paired-plan-count" id="paired-seed-note">{pairCount} pares planejados · até {requiredRuns} execuções SUMO · até {requiredWall}s. Revise o orçamento para cobrir a matriz ou habilite explicitamente plano incompleto.</p>
    <p className="paired-adapter-note">POST/GET usam o contrato implementado em <code>/api/v1/mobility-experiments</code>. A referência à Arena é caller-asserted no backend e não verificada contra a instância anual.</p>{error&&<div className="paired-error" role="alert">{error}</div>}<button className="primary-button" disabled={busy} type="submit">{busy?'Criando manifesto…':'Criar experimento'}</button></form>;
}
function parseIntegerListSafe(raw:string){try{return parseIntegerList(raw,'Seeds')}catch{return [];}}
function parseStrategyCount(raw:string){try{const v=JSON.parse(raw);return Array.isArray(v)?v.length:0}catch{return 0}}

function SummaryTable({ experiment }: { experiment: PairedExperiment }) {
  return <section className="paired-results" aria-labelledby="paired-summary-title">
    <div className="paired-section-heading"><div><p className="eyebrow">RESUMOS SEGREGADOS POR JANELA</p><h3 id="paired-summary-title">Distribuição e incerteza</h3></div><p>Os ICs são marginais e condicionais à aleatoriedade operacional do SUMO.</p></div>
    {experiment.summaries_by_window.length === 0 ? <p className="paired-empty">Sem resumos disponíveis para as janelas planejadas.</p> : <><div className="paired-table-scroll" tabIndex={0} aria-label="Resumos por janela, estratégia e métrica; use as setas ou rolagem para navegar">
      <table><caption>Resumo por janela, estratégia e métrica. Cada linha permanece separada por janela.</caption><thead><tr><th scope="col">Janela</th><th scope="col">Estratégia</th><th scope="col">Métrica</th><th scope="col">Período</th><th scope="col">Viagens solicitadas / concluídas / não concluídas (baseline · estratégia)</th><th scope="col">n completo / planejado</th><th scope="col">Baseline e estratégia: média · DP · mediana · IIQ · mín–máx</th><th scope="col">Δ pareado: média · DP · mediana · IIQ · mín–máx</th><th scope="col">IC t 95% da média Δ</th><th scope="col">Método / proveniência</th></tr></thead>
        <tbody>{experiment.summaries_by_window.map((item, index) => <tr key={`${item.window_id}-${item.strategy_id}-${item.metric_id}-${index}`}>
          <th scope="row">{item.window_id}</th><td>{item.strategy_id}</td><td>{metricLabel(item.metric_id)} <small>({item.unit})</small></td><td>{item.period === 'demand_window' ? 'Janela de demanda' : 'Viagens concluídas até o escoamento'}</td><td>{(['trips_requested','trips_completed','trips_not_completed'] as const).map((metricId) => { const count = experiment.summaries_by_window.find(row => row.window_id === item.window_id && row.strategy_id === item.strategy_id && row.metric_id === metricId); return <div key={metricId}>{metricLabel(metricId)}: {count ? `${format(count.arm_summary.baseline.mean)} · ${format(count.arm_summary.strategy.mean)}` : 'Não disponível'}</div>; })}</td><td>{item.n_complete} / {item.n_planned}</td><td>B {format(item.arm_summary.baseline.mean)} · {format(item.arm_summary.baseline.sd)} · {format(item.arm_summary.baseline.median)} · {format(item.arm_summary.baseline.iqr)} · {format(item.arm_summary.baseline.min)}–{format(item.arm_summary.baseline.max)}<br/>E {format(item.arm_summary.strategy.mean)} · {format(item.arm_summary.strategy.sd)} · {format(item.arm_summary.strategy.median)} · {format(item.arm_summary.strategy.iqr)} · {format(item.arm_summary.strategy.min)}–{format(item.arm_summary.strategy.max)}</td><td>{format(item.paired_delta_summary.mean, true)} · {format(item.paired_delta_summary.sd)} · {format(item.paired_delta_summary.median, true)} · {format(item.paired_delta_summary.iqr)} · {format(item.paired_delta_summary.min, true)}–{format(item.paired_delta_summary.max, true)}</td><td>{experiment.status !== 'succeeded' || item.n_complete !== item.n_planned || item.confidence_interval.n !== item.n_planned ? 'Não inferir · conjunto incompleto' : item.confidence_interval.n < 2 ? 'Indisponível · n < 2' : `${format(item.confidence_interval.lower, true)} a ${format(item.confidence_interval.upper, true)} (n=${item.confidence_interval.n}, gl=${item.confidence_interval.degrees_of_freedom})`}</td><td>{item.confidence_interval.method} · {item.provenance_kind} · {item.method_version}</td>
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
    <p className="paired-note">Cada par reúne baseline e estratégia com entradas comuns identificadas por hash. `route_exposure` indica somente passagem de rota pela área alterada; não identifica veículos afetados. A API inclui todas as combinações planejadas; pares queued e seus IDs são mostrados como faltantes.</p>
    {experiment.pairs.length === 0 ? <p className="paired-empty">O DTO não contém linhas de pares. A ausência permanece explícita; contadores planejados não são convertidos em resultados.</p> : <div className="paired-pair-list">
      {visiblePairs.map((pair, index) => <details className="paired-pair" key={`${pair.pair_id}-${index}`}>
        <summary><span className={statusClass(`state-${pairOutcome(pair)}`)}>{pairOutcomeLabel(pairOutcome(pair))}</span><strong>{pair.window_id}</strong><span>Seed {pair.seed}</span><span>{pair.strategy_id}</span><code>{pair.pair_id}</code><span>Rotas: {pair.route_exposure === 'unknown' ? 'desconhecido' : pair.route_exposure === 'exposed' ? 'cruzam a área' : 'sem cruzamento identificado'}</span></summary>
        <div className="paired-pair-content"><dl className="paired-identities"><div><dt>Estado retornado</dt><dd>{pair.status}</dd></div><div><dt>Estado derivado dos braços e delta</dt><dd>{pairOutcomeLabel(pairOutcome(pair))}</dd></div><div><dt>Pair ID</dt><dd>{pair.pair_id}</dd></div><div><dt>Hash de entrada comum</dt><dd>{pair.common_input_sha256}</dd></div><div><dt>Execução baseline</dt><dd>{pair.baseline_execution_id} · {executionLabel[pair.executions.baseline.status]}</dd></div><div><dt>Execução estratégia</dt><dd>{pair.strategy_execution_id} · {executionLabel[pair.executions.strategy.status]}</dd></div></dl>
          <div className="paired-arm-grid">{(['baseline', 'strategy'] as const).map((arm) => <div key={arm}><h4>{arm === 'baseline' ? 'Baseline' : `Estratégia · ${pair.strategy_id}`}</h4><p>{pair.executions[arm].attempts.length} tentativas</p><ul>{pair.executions[arm].attempts.map((attempt, i) => <li key={`${attempt.attempt}-${i}`}>Tentativa {attempt.attempt} · {executionLabel[attempt.status]}{attempt.error ? ` · ${attempt.error}` : ''}{attempt.artifact_sha256 ? ` · artefato ${attempt.artifact_sha256.slice(0, 12)}…` : ''}</li>)}</ul></div>)}</div>
          {(pair.baseline_metrics || pair.strategy_metrics || pair.deltas || pair.executions.baseline.result_metrics || pair.executions.strategy.result_metrics) && <div className="paired-values"><h4>{pairOutcome(pair) === 'completed' ? 'Valores e deltas (estratégia − baseline)' : 'Resultados do braço concluído · sem delta pareado'}</h4><div className="paired-table-scroll" tabIndex={0} aria-label={`Métricas do par ${pair.pair_id}`}><table><caption>Métricas disponíveis por braço; deltas somente para pares completos</caption><thead><tr><th scope="col">Métrica</th><th scope="col">Baseline</th><th scope="col">Estratégia</th><th scope="col">Delta</th><th scope="col">Proveniência por valor</th></tr></thead><tbody>{Array.from(new Set([...Object.keys(pair.baseline_metrics ?? {}), ...Object.keys(pair.strategy_metrics ?? {}), ...Object.keys(pair.deltas ?? {}), ...Object.keys(pair.executions.baseline.result_metrics ?? {}), ...Object.keys(pair.executions.strategy.result_metrics ?? {})])).map((id) => {
            const base = pair.baseline_metrics?.[id]; const strategy = pair.strategy_metrics?.[id]; const delta = pair.deltas?.[id]; const rawBase = pair.executions.baseline.result_metrics?.[id]; const rawStrategy = pair.executions.strategy.result_metrics?.[id];
            return <tr key={id}><th scope="row">{metricLabel(id)}</th><td>{base ? format(base.value) : rawBase !== undefined ? <>{format(rawBase)} · bruto<br/><small>{pair.executions.baseline.metric_methods[id] ?? 'método não disponível'} · artefato {pair.executions.baseline.artifact_sha256 ?? 'não disponível'}</small></> : 'Métrica não disponível'}</td><td>{strategy ? format(strategy.value) : rawStrategy !== undefined ? <>{format(rawStrategy)} · bruto<br/><small>{pair.executions.strategy.metric_methods[id] ?? 'método não disponível'} · artefato {pair.executions.strategy.artifact_sha256 ?? 'não disponível'}</small></> : 'Métrica não disponível'}</td><td>{delta ? format(delta.value, true) : 'Métrica não disponível'}</td><MetricProvenanceCell baseline={base} strategy={strategy} delta={delta} rawBaseline={rawBase !== undefined ? { method: pair.executions.baseline.metric_methods[id] ?? 'método não disponível', artifact: pair.executions.baseline.artifact_sha256 } : undefined} rawStrategy={rawStrategy !== undefined ? { method: pair.executions.strategy.metric_methods[id] ?? 'método não disponível', artifact: pair.executions.strategy.artifact_sha256 } : undefined} /></tr>;
          })}</tbody></table></div></div>}
          {pairOutcome(pair) !== 'completed' && <p className="paired-missing">Par sem resultado válido completo. As métricas indisponíveis não são mostradas como zero.</p>}
        </div>
      </details>)}
      {experiment.pairs.length > shown && <button className="quiet-button paired-more" type="button" onClick={() => setShown((current) => Math.min(experiment.pairs.length, current + PAGE_SIZE))}>Mostrar mais {Math.min(PAGE_SIZE, experiment.pairs.length - shown)} pares ({shown} de {experiment.pairs.length})</button>}
    </div>}
  </section>;
}

export function ExperimentDetails({ experiment, onRetry, onResume, onCancel, busy, cancelPending = false, cancellationAcknowledged = false }: { experiment: PairedExperiment; onRetry: () => void; onResume: () => void; onCancel: () => void; busy: boolean; cancelPending?: boolean; cancellationAcknowledged?: boolean }) {
  const active = experiment.status === 'queued' || experiment.status === 'running';
  const cancellable = active || experiment.status === 'partial';
  const cancellationRequested = experiment.cancellation_requested || cancellationAcknowledged;
  return <div className="paired-experiment-result">
    <div className="paired-overview"><div><p className="eyebrow">EXPERIMENTO · {experiment.dto_schema_version} / PROTOCOLO {experiment.protocol_version}</p><h3>{experiment.experiment_id}</h3></div><span className={statusClass(experiment.status)} role="status">{statusLabel[experiment.status]}</span></div>
    <div className="paired-counts" aria-label="Contagem de pares"><div><strong>{experiment.planned_pairs}</strong><span>Planejados</span></div><div><strong>{experiment.completed_pairs}</strong><span>Completos</span></div><div><strong>{experiment.failed_pairs}</strong><span>Falhos</span></div><div><strong>{experiment.running_pairs}</strong><span>Em execução</span></div><div><strong>{experiment.missing_pairs}</strong><span>Faltantes</span></div></div>
    <p className="paired-sr-only" aria-live="polite">Estado {statusLabel[experiment.status]}. Planejados {experiment.planned_pairs}; completos {experiment.completed_pairs}; falhos {experiment.failed_pairs}; em execução {experiment.running_pairs}; faltantes {experiment.missing_pairs}.</p>
    {experiment.status === 'partial' && <div className="paired-missing" role="status"><strong>Resultado parcial e incompleto.</strong> Os resumos são apenas descritivos de pares completos, sujeitos à seleção por falhas. IC inferencial está oculto nesta apresentação.</div>}
    {cancelPending && <p className="paired-live" role="status" aria-live="polite">Solicitando cancelamento…</p>}
    {cancellationRequested && !cancelPending && <p className="paired-live" role="status" aria-live="polite">Cancelamento solicitado; atualize o estado para confirmar a conclusão.</p>}
    {active && !cancellationRequested && !cancelPending && <p className="paired-live" role="status" aria-live="polite">Atualizando o experimento automaticamente…</p>}
    <dl className="paired-manifest"><div><dt>Manifesto do experimento</dt><dd>{experiment.manifest_sha256}</dd></div><div><dt>Manifesto da Arena referenciado</dt><dd>{experiment.arena_manifest_id} · {experiment.arena_manifest_sha256}</dd></div><div><dt>Execuções planejadas</dt><dd>{experiment.planned_executions}</dd></div><div><dt>SUMO utilizado</dt><dd>{experiment.sumo_runs_used} · {experiment.wall_clock_seconds_used}s usados · {experiment.reserved_wall_clock_seconds}s reservados</dd></div><div><dt>Manifesto congelado</dt><dd><details><summary>Ver parâmetros e proveniência</summary><pre>{JSON.stringify(experiment.manifest,null,2)}</pre></details></dd></div></dl>
    <dl className="paired-manifest"><div><dt>Código de erro</dt><dd>{experiment.error_code ?? 'Não informado'}</dd></div><div><dt>Motivo de parada</dt><dd>{experiment.stop_reason ?? 'Não informado'}</dd></div></dl><SummaryTable experiment={experiment} />
    <PairList experiment={experiment} />
    <section className="paired-caveats" aria-labelledby="paired-limitations-title"><h3 id="paired-limitations-title">Escopo e limites de interpretação</h3><ul>{experiment.limitations.map((item) => <li key={item}>{item.replaceAll('_', ' ')}</li>)}</ul><p>Aurora, a rede, a demanda e as intervenções são sintéticas. Resultados SUMO cobrem somente a janela e o escoamento configurado; filas agregam a rede e tempo/velocidade cobrem viagens concluídas até o fim do escoamento. Não há efeito isolado nos veículos expostos. Resultados não são anualizados e não sustentam inferência sobre tráfego real nem alegação causal. `route_exposure` indica passagem de uma rota pela área alterada; não segmenta resultados nem identifica veículos afetados.</p></section>
    {cancellable && !cancellationRequested && !cancelPending && <div className="paired-actions"><button className="quiet-button paired-cancel" type="button" disabled={busy} onClick={onCancel}>Cancelar experimento</button></div>}
    {(experiment.status === 'partial' || experiment.status === 'failed') ? <div className="paired-actions"><button className="quiet-button" type="button" disabled={busy} onClick={onRetry}>Atualizar estado</button>{!cancellationRequested && <button className="primary-button" type="button" disabled={busy} onClick={onResume}>{busy ? 'Solicitando retomada…' : 'Retomar pares incompletos'}</button>}</div> : null}
  </div>;
}

export function CreatedExperimentNotice({ experimentId }: { experimentId: string }) {
  return <p className="paired-live" role="status">Experimento criado enquanto outra seleção estava aberta. ID do novo experimento: <code>{experimentId}</code>. Copie este ID para carregá-lo.</p>;
}

export function PairedExperimentPanel() {
  const [experiment, setExperiment] = useState<PairedExperiment | null>(null);
  const [expectedPlan, setExpectedPlan] = useState<ExpectedExperimentPlan | null>(null);
  const [lookupId, setLookupId] = useState('');
  const [busy, setBusy] = useState(false);
  const [cancelPendingIds, setCancelPendingIds] = useState<Set<string>>(() => new Set());
  const [cancellationAcknowledgedIds, setCancellationAcknowledgedIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState('');
  const [createdWhileViewingAnotherExperiment, setCreatedWhileViewingAnotherExperiment] = useState('');
  const [failedLookupId, setFailedLookupId] = useState('');
  const selectedExperimentId = useRef<string | null>(null);
  const [selectedExperimentIdForView, setSelectedExperimentIdForView] = useState<string | null>(null);
  const selectionGeneration = useRef(0);
  const [selectionRevision, setSelectionRevision] = useState(0);
  const busyOperationCount = useRef(0);
  const beginBusyOperation = () => { busyOperationCount.current += 1; setBusy(true); };
  const endBusyOperation = () => { busyOperationCount.current = Math.max(0, busyOperationCount.current - 1); setBusy(busyOperationCount.current > 0); };
  const reconcileCancellationAcknowledgement = (updated: PairedExperiment) => {
    if (!updated.cancellation_requested && updated.status !== 'cancelled') return;
    setCancellationAcknowledgedIds((current) => {
      if (!current.has(updated.experiment_id)) return current;
      const next = new Set(current);
      next.delete(updated.experiment_id);
      return next;
    });
  };
  const beginSelection = (experimentId: string | null) => {
    const generation = ++selectionGeneration.current;
    selectedExperimentId.current = experimentId;
    setSelectedExperimentIdForView(experimentId);
    setSelectionRevision(generation);
    return generation;
  };
  const selectExperiment = (selected: PairedExperiment, generation = selectionGeneration.current) => {
    if (generation !== selectionGeneration.current) return false;
    selectedExperimentId.current = selected.experiment_id;
    setSelectedExperimentIdForView(selected.experiment_id);
    reconcileCancellationAcknowledgement(selected);
    setExperiment(selected);
    return true;
  };
  const active = !!experiment && (experiment.status === 'queued' || experiment.status === 'running') && !cancelPendingIds.has(experiment.experiment_id);

  useEffect(() => {
    if (!active || !experiment || selectedExperimentIdForView !== experiment.experiment_id) return;
    const controller = new AbortController();
    let timer: number;
    const generation = selectionGeneration.current;
    const poll = async () => {
      try {
        const updated = await fetchPairedExperiment(experiment.experiment_id, controller.signal, expectedPlan ?? undefined);
        if (controller.signal.aborted || !isCurrentExperimentRequest(generation, selectionGeneration.current, experiment.experiment_id, selectedExperimentId.current)) return;
        reconcileCancellationAcknowledgement(updated);
        setExperiment(updated);
        setError('');
        if (updated.status === 'queued' || updated.status === 'running') timer = window.setTimeout(poll, 1500);
      } catch (reason) {
        if (!controller.signal.aborted && isCurrentExperimentRequest(generation, selectionGeneration.current, experiment.experiment_id, selectedExperimentId.current)) {
          setError(reason instanceof Error ? reason.message : 'Não foi possível atualizar o experimento.');
          timer = window.setTimeout(poll, 3000);
        }
      }
    };
    timer = window.setTimeout(poll, 1500);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [active, experiment?.experiment_id, experiment?.status, expectedPlan, selectedExperimentIdForView, selectionRevision]);

  const lookup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const id = lookupId.trim(); const previousId = selectedExperimentId.current; const previousPlan = expectedPlan; const generation = beginSelection(id); beginBusyOperation(); setError(''); setFailedLookupId(id);
    const plan = experiment?.experiment_id === id ? expectedPlan : null;
    try { const loaded = await fetchPairedExperiment(id, undefined, plan ?? undefined); if (selectExperiment(loaded, generation)) { setExpectedPlan(plan); setFailedLookupId(''); } }
    catch (reason) { if (selectionGeneration.current === generation) { beginSelection(previousId); setExpectedPlan(previousPlan); setError(reason instanceof Error ? reason.message : 'Não foi possível carregar o experimento.'); } }
    finally { endBusyOperation(); }
  };
  const retry = () => {
    const id = failedLookupId || experiment?.experiment_id;
    if (!id) return;
    const previousId = selectedExperimentId.current; const previousPlan = expectedPlan; const generation = beginSelection(id); beginBusyOperation(); setLookupId(id); setError('');
    const plan = experiment?.experiment_id === id ? expectedPlan : null;
    void fetchPairedExperiment(id, undefined, plan ?? undefined).then((loaded) => { if (selectExperiment(loaded, generation)) { setExpectedPlan(plan); setFailedLookupId(''); } }).catch((reason: unknown) => { if (selectionGeneration.current === generation) { beginSelection(previousId); setExpectedPlan(previousPlan); setError(reason instanceof Error ? reason.message : 'Falha ao tentar novamente.'); } }).finally(endBusyOperation);
  };

  const resume = async () => { if (!experiment || !['partial','failed'].includes(experiment.status) || experiment.cancellation_requested || cancellationAcknowledgedIds.has(experiment.experiment_id)) return; const id = experiment.experiment_id; const generation = selectionGeneration.current; beginBusyOperation(); setError(''); try { const updated = await retryPairedExperiment(id, expectedPlan ?? undefined); if (selectionGeneration.current === generation && selectedExperimentId.current === id) selectExperiment(updated, generation); } catch (reason) { if (selectionGeneration.current === generation && selectedExperimentId.current === id) setError(reason instanceof Error ? reason.message : 'Não foi possível retomar pares incompletos.'); } finally { endBusyOperation(); } };
  const cancel = async () => { if (!experiment || !['queued','running','partial'].includes(experiment.status) || experiment.cancellation_requested || cancellationAcknowledgedIds.has(experiment.experiment_id) || cancelPendingIds.has(experiment.experiment_id)) return; const id = experiment.experiment_id; const generation = beginSelection(id); setCancelPendingIds((current) => new Set(current).add(id)); setError(''); try { const updated = await cancelAndRefreshPairedExperiment(id, expectedPlan ?? undefined, (acknowledgedId) => setCancellationAcknowledgedIds((current) => rememberCancellationAcknowledgement(current, acknowledgedId))); if (selectionGeneration.current === generation && selectedExperimentId.current === id) selectExperiment(updated, generation); } catch (reason) { if (selectionGeneration.current === generation && selectedExperimentId.current === id) setError(reason instanceof Error ? reason.message : 'Não foi possível cancelar o experimento.'); } finally { setCancelPendingIds((current) => { const next = new Set(current); next.delete(id); return next; }); } };

  return <section className="simulation-panel paired-panel" aria-labelledby="paired-experiment-title">
    <div className="section-heading"><div><p className="eyebrow">PROTOCOLO DE EXPERIMENTO PAREADO · MULTI-SEED</p><h2 id="paired-experiment-title">Experimento SUMO por janela</h2></div><span className="synthetic-pill">AURORA SINTÉTICA</span></div>
    <p className="simulation-description">Compare cada estratégia com o mesmo baseline, snapshot, demanda expandida, janela e seed. Seeds variam somente a aleatoriedade operacional do SUMO; não amostram demanda. Resumos e incerteza permanecem separados por janela.</p>
    <ExperimentCreateForm onCreateStarted={() => { setCreatedWhileViewingAnotherExperiment(''); return beginSelection(selectedExperimentId.current); }} onCreated={(created, input, generation) => { if (!shouldSelectCreatedExperiment(generation, selectionGeneration.current)) { setCreatedWhileViewingAnotherExperiment(created.experiment_id); return; } if (!selectExperiment(created, generation)) return; const plan = { window_ids: input.window_ids, strategies: input.strategies, seeds: input.seeds, metrics: input.metrics, primary_metrics: input.primary_metrics }; setExpectedPlan(plan); setLookupId(created.experiment_id); setFailedLookupId(''); setError(''); }} />
    {createdWhileViewingAnotherExperiment && <CreatedExperimentNotice experimentId={createdWhileViewingAnotherExperiment} />}
    <form className="paired-lookup" onSubmit={lookup}><label htmlFor="paired-lookup-id">Acompanhar experimento existente</label><input id="paired-lookup-id" value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder="experiment_id" required /><button className="quiet-button" disabled={busy} type="submit">{busy ? 'Carregando…' : 'Carregar'}</button></form>
    {error && <div className="paired-error" role="alert"><strong>Não foi possível carregar ou atualizar o experimento.</strong><p>{error}</p><button className="quiet-button" type="button" disabled={busy} onClick={retry}>Tentar novamente</button></div>}
    {experiment && <ExperimentDetails experiment={experiment} onRetry={retry} onResume={resume} onCancel={cancel} busy={busy || cancelPendingIds.has(experiment.experiment_id)} cancelPending={cancelPendingIds.has(experiment.experiment_id)} cancellationAcknowledged={cancellationAcknowledgedIds.has(experiment.experiment_id)} />}
  </section>;
}

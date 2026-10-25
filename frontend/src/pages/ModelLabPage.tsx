import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { datasetApi, trainingApi, modelsApi } from '../services/api';
import { useTheme } from '../context/ThemeContext';
import { Dataset, TrainingRun, ModelComparisonResponse, CandidateModel } from '../types';
import {
  Cpu,
  CheckCircle2,
  AlertTriangle,
  Award,
  Zap,
  Clock,
  HardDrive,
  BarChart2,
  TrendingUp,
  Sparkles,
  ArrowRight,
  Check,
  RefreshCw,
  Info,
  Activity,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts';

export const ModelLabPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isDark } = useTheme();

  const initialRunId = searchParams.get('run_id');
  const initialDatasetId = searchParams.get('dataset_id');

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(initialDatasetId || '');
  const [runs, setRuns] = useState<TrainingRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId || '');
  const [comparison, setComparison] = useState<ModelComparisonResponse | null>(null);
  const [selectedModel, setSelectedModel] = useState<CandidateModel | null>(null);

  const [loading, setLoading] = useState(false);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // 1. Fetch datasets
  useEffect(() => {
    datasetApi.list(1, 50).then((res) => {
      setDatasets(res.items);
      if (!selectedDatasetId && res.items.length > 0) {
        setSelectedDatasetId(res.items[0].id);
      }
    });
  }, []);

  // 2. Fetch runs when dataset changes
  useEffect(() => {
    if (!selectedDatasetId) return;
    trainingApi.listRuns(selectedDatasetId).then((runList) => {
      setRuns(runList);
      if (runList.length > 0) {
        // If query param matches, keep it; otherwise pick first completed run
        const match = runList.find((r) => r.id === selectedRunId);
        if (!match) {
          const completed = runList.find((r) => r.status === 'COMPLETED') || runList[0];
          setSelectedRunId(completed.id);
        }
      } else {
        setSelectedRunId('');
        setComparison(null);
        setSelectedModel(null);
      }
    });
  }, [selectedDatasetId]);

  // 3. Fetch comparison when run changes
  useEffect(() => {
    if (!selectedRunId) return;
    setLoading(true);
    trainingApi
      .getComparison(selectedRunId)
      .then((data) => {
        setComparison(data);
        if (data.metrics_table.length > 0) {
          // Select active model or first successful model
          const active = data.metrics_table.find((m) => m.is_active);
          setSelectedModel(active || data.metrics_table[0]);
        }
      })
      .catch((err) => {
        console.error('Failed to load model comparison:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [selectedRunId]);

  const handleActivateModel = async (modelId: string) => {
    const targetModel = comparison?.metrics_table.find((m) => m.id === modelId);
    const baselineComp = targetModel?.evaluation_summary?.baseline_comparison;
    const beatsBaseline = baselineComp?.beats_baseline;

    if (beatsBaseline === false) {
      const metricName = baselineComp?.primary_metric?.toUpperCase() || comparison?.primary_metric?.toUpperCase() || 'PRIMARY METRIC';
      const candVal = baselineComp?.candidate_value ?? targetModel?.metrics?.[comparison?.primary_metric || ''];
      const baseVal = baselineComp?.baseline_value;
      const proceed = window.confirm(
        `⚠️ EVIDENCE WARNING: Subpar Performance\n\n` +
        `This model (${targetModel?.algorithm_display_name}) did NOT outperform the baseline on ${metricName}.\n` +
        `Candidate: ${candVal !== undefined ? candVal : '--'} vs Baseline: ${baseVal !== undefined ? baseVal : '--'}\n\n` +
        `Promoting a model that does not beat the baseline may degrade production performance.\n\n` +
        `Are you sure you want to promote this model to Active Production?`
      );
      if (!proceed) return;
    } else {
      const proceed = window.confirm(
        `Promote ${targetModel?.algorithm_display_name || 'this model'} to Active Production?\n\n` +
        `This model will become the champion model used for all future predictions on this dataset.`
      );
      if (!proceed) return;
    }

    setActivatingId(modelId);
    setActionSuccess(null);
    try {
      await modelsApi.activate(modelId);
      setActionSuccess('Model promoted to active production model!');
      // Refresh comparison
      if (selectedRunId) {
        const updated = await trainingApi.getComparison(selectedRunId);
        setComparison(updated);
        const match = updated.metrics_table.find((m) => m.id === modelId);
        if (match) setSelectedModel(match);
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to activate model');
    } finally {
      setActivatingId(null);
    }
  };

  // Prepare chart data for metrics comparison
  const metricChartData =
    comparison?.metrics_table.map((m) => {
      const primaryVal =
        m.metrics?.[comparison.primary_metric] !== undefined
          ? Number(Number(m.metrics[comparison.primary_metric]).toFixed(4))
          : 0;
      return {
        name: m.algorithm_display_name,
        [comparison.primary_metric.toUpperCase()]: primaryVal,
        duration: m.training_duration_seconds,
      };
    }) || [];

  // Prepare sample predictions chart data
  const samplePredChartData =
    selectedModel?.sample_predictions?.slice(0, 30).map((p, idx) => ({
      index: idx + 1,
      Actual: typeof p.actual === 'number' ? Number(p.actual.toFixed(2)) : p.actual,
      Predicted: typeof p.predicted === 'number' ? Number(p.predicted.toFixed(2)) : p.predicted,
    })) || [];

  // Prepare feature importances data
  const featureImpData = selectedModel?.feature_importances
    ? Object.entries(selectedModel.feature_importances)
        .map(([k, v]) => ({
          feature: k,
          importance: Number((v * 100).toFixed(2)),
        }))
        .sort((a, b) => b.importance - a.importance)
        .slice(0, 10)
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 border-b border-slate-200/80 dark:border-slate-800 gap-4">
        <div>
          <div className="flex items-center space-x-2 text-brand-600 dark:text-brand-400 text-xs font-bold uppercase tracking-wider">
            <Cpu className="w-4 h-4" />
            <span>Phase D & E • Automated Machine Learning</span>
          </div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-slate-100 tracking-tight mt-1">Model Lab & Evaluation</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Compare candidate algorithms, analyze validation curves, and promote the champion model to production.
          </p>
        </div>

        {/* Dataset & Run Selectors */}
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <label className="block text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">
              Dataset
            </label>
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className="bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-xs font-semibold px-3 py-2 text-slate-800 dark:text-slate-200 focus:ring-brand-500 focus:border-brand-500"
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.row_count} rows)
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">
              Training Run
            </label>
            <select
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              disabled={runs.length === 0}
              className="bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-xs font-semibold px-3 py-2 text-slate-800 dark:text-slate-200 focus:ring-brand-500 focus:border-brand-500 disabled:opacity-50"
            >
              {runs.length === 0 ? (
                <option value="">No training runs found</option>
              ) : (
                runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.task_type.toUpperCase()} • {r.status} ({new Date(r.created_at).toLocaleDateString()})
                  </option>
                ))
              )}
            </select>
          </div>

          <button
            onClick={() => navigate('/predictions')}
            className="inline-flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm self-end"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Generate Predictions</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {actionSuccess && (
        <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center space-x-2">
          <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {loading ? (
        <div className="p-16 text-center text-slate-400 text-sm">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-brand-600 dark:text-brand-400" />
          Loading candidate model evaluations...
        </div>
      ) : !comparison || comparison.metrics_table.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-12 text-center max-w-xl mx-auto shadow-sm">
          <Cpu className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800 dark:text-slate-200">No Model Results Available</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-md mx-auto">
            This dataset has not completed a training run yet. Go to the Dataset Configuration tab to start training candidate models.
          </p>
          {selectedDatasetId && (
            <button
              onClick={() => navigate(`/datasets/${selectedDatasetId}`)}
              className="mt-4 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm"
            >
              Open Dataset Details
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          {/* Metadata Card */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs transition-colors">
            <div>
              <span className="text-slate-400 dark:text-slate-500 font-semibold uppercase text-[10px] block">Task Type</span>
              <span className="font-bold text-slate-900 dark:text-slate-100 uppercase">{comparison.task_type}</span>
            </div>
            <div>
              <span className="text-slate-400 dark:text-slate-500 font-semibold uppercase text-[10px] block">Target Variable</span>
              <span className="font-mono font-bold text-slate-900 dark:text-slate-100">{comparison.target_column || 'None (Unsupervised)'}</span>
            </div>
            <div>
              <span className="text-slate-400 dark:text-slate-500 font-semibold uppercase text-[10px] block">Primary Metric</span>
              <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 uppercase">
                {comparison.task_type === 'anomaly' ? 'Observed Anomaly Rate' : comparison.primary_metric}
              </span>
            </div>
            <div>
              <span className="text-slate-400 dark:text-slate-500 font-semibold uppercase text-[10px] block">Candidate Models</span>
              <span className="font-bold text-slate-900 dark:text-slate-100">{comparison.metrics_table.length} trained</span>
            </div>
          </div>

          {/* Diagnostic Note for Anomaly Detection */}
          {comparison.task_type === 'anomaly' && (
            <div className="p-4 bg-blue-50/70 dark:bg-blue-950/40 border border-blue-200/80 dark:border-blue-900/50 rounded-2xl flex items-start space-x-3 text-xs text-blue-800 dark:text-blue-300">
              <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
              <div>
                <span className="font-bold block text-sm">Unsupervised Anomaly Diagnostics</span>
                <span className="mt-0.5 block leading-relaxed text-blue-700/90 dark:text-blue-300/80">
                  Ground-truth anomaly labels are unavailable. Observed anomaly rates and flagged counts are diagnostic distribution metrics describing decision boundary density, not supervised accuracy or detection quality scores.
                </span>
              </div>
            </div>
          )}

          {/* Model Comparison Leaderboard Table */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden shadow-sm transition-colors">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  {comparison.task_type === 'anomaly' ? 'Candidate Models & Diagnostics' : 'Candidate Models Leaderboard'}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {comparison.task_type === 'anomaly'
                    ? 'Evaluated on validation partition with observed anomaly density.'
                    : `Ranked by ${comparison.primary_metric.toUpperCase()} performance on validation partition.`}
                </p>
              </div>
            </div>

            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-300 font-semibold uppercase">
                    <th className="py-3 px-4">Rank</th>
                    <th className="py-3 px-4">Algorithm Name</th>
                    <th className="py-3 px-4">Family</th>
                    {comparison.task_type in { regression: 1, forecasting: 1 } && (
                      <>
                        <th className="py-3 px-4 font-mono">{comparison.primary_metric.toUpperCase()}</th>
                        <th className="py-3 px-4 font-mono">{comparison.primary_metric === 'mae' ? 'RMSE' : 'MAE'}</th>
                        <th className="py-3 px-4 font-mono">R² SCORE</th>
                      </>
                    )}
                    {comparison.task_type === 'classification' && (
                      <>
                        <th className="py-3 px-4 font-mono">MACRO-F1</th>
                        <th className="py-3 px-4 font-mono">WEIGHTED-F1</th>
                        <th className="py-3 px-4 font-mono">ACCURACY</th>
                        <th className="py-3 px-4 font-mono">ROC-AUC</th>
                      </>
                    )}
                    {comparison.task_type === 'anomaly' && (
                      <>
                        <th className="py-3 px-4 font-mono">OBSERVED ANOMALY %</th>
                        <th className="py-3 px-4 font-mono">FLAGGED COUNT</th>
                        <th className="py-3 px-4 font-mono">CONFIGURED CONTAMINATION</th>
                      </>
                    )}
                    {comparison.task_type !== 'anomaly' && (
                      <th className="py-3 px-4 font-mono">VS BASELINE</th>
                    )}
                    <th className="py-3 px-4">Duration</th>
                    <th className="py-3 px-4">Artifact</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Production Deployment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {comparison.metrics_table.map((model, idx) => {
                    const isSelected = selectedModel?.id === model.id;
                    const isAnomaly = comparison.task_type === 'anomaly';

                    return (
                      <tr
                        key={model.id}
                        onClick={() => setSelectedModel(model)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-indigo-50/60 dark:bg-indigo-950/40' : 'hover:bg-slate-50/50 dark:hover:bg-slate-800/40'
                        }`}
                      >
                        <td className="py-3.5 px-4 font-bold text-slate-400 dark:text-slate-500">
                          {!isAnomaly && idx === 0 ? (
                            <span className="inline-flex items-center text-amber-600 dark:text-amber-400 font-black">
                              <Award className="w-4 h-4 mr-1 text-amber-500" /> #1
                            </span>
                          ) : (
                            `#${idx + 1}`
                          )}
                        </td>
                        <td className="py-3.5 px-4 font-bold text-slate-900 dark:text-slate-100">
                          <div className="flex items-center space-x-2">
                            <span>{model.algorithm_display_name}</span>
                            {model.is_active && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 font-extrabold uppercase">
                                Active
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3.5 px-4 uppercase text-slate-500 dark:text-slate-400 font-medium text-[11px]">
                          {model.model_family}
                        </td>
                        {comparison.task_type in { regression: 1, forecasting: 1 } && (
                          <>
                            <td className="py-3.5 px-4 font-mono font-bold text-indigo-700 dark:text-indigo-400">
                              {model.metrics?.[comparison.primary_metric] !== undefined
                                ? Number(model.metrics[comparison.primary_metric]).toFixed(4)
                                : '--'}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {comparison.primary_metric === 'mae'
                                ? (model.metrics?.rmse !== undefined ? Number(model.metrics.rmse).toFixed(4) : '--')
                                : (model.metrics?.mae !== undefined ? Number(model.metrics.mae).toFixed(4) : '--')}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {model.metrics?.r2 !== undefined ? Number(model.metrics.r2).toFixed(4) : '--'}
                            </td>
                          </>
                        )}
                        {comparison.task_type === 'classification' && (
                          <>
                            <td className="py-3.5 px-4 font-mono font-bold text-indigo-700 dark:text-indigo-400">
                              {model.metrics?.macro_f1 !== undefined
                                ? Number(model.metrics.macro_f1).toFixed(4)
                                : (model.metrics?.f1 !== undefined ? Number(model.metrics.f1).toFixed(4) : '--')}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {model.metrics?.weighted_f1 !== undefined ? Number(model.metrics.weighted_f1).toFixed(4) : '--'}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {model.metrics?.accuracy !== undefined
                                ? `${(Number(model.metrics.accuracy) * 100).toFixed(1)}%`
                                : '--'}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {model.metrics?.roc_auc !== undefined ? Number(model.metrics.roc_auc).toFixed(4) : '--'}
                            </td>
                          </>
                        )}
                        {comparison.task_type === 'anomaly' && (
                          <>
                            <td className="py-3.5 px-4 font-mono font-bold text-indigo-700 dark:text-indigo-400">
                              {model.metrics?.observed_anomaly_pct !== undefined
                                ? `${model.metrics.observed_anomaly_pct}%`
                                : (model.metrics?.contamination_rate !== undefined
                                    ? `${(Number(model.metrics.contamination_rate) * (Number(model.metrics.contamination_rate) <= 1.0 ? 100 : 1)).toFixed(2)}%`
                                    : '--')}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {model.metrics?.anomalies_detected !== undefined
                                ? `${model.metrics.anomalies_detected} / ${model.metrics.total_observations ?? '--'}`
                                : '--'}
                            </td>
                            <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-400">
                              {model.metrics?.configured_contamination_pct !== undefined
                                ? `${model.metrics.configured_contamination_pct}%`
                                : (model.hyperparameters?.contamination !== undefined
                                    ? `${(Number(model.hyperparameters.contamination) * 100).toFixed(1)}%`
                                    : '5.0%')}
                            </td>
                          </>
                        )}
                        {comparison.task_type !== 'anomaly' && (
                          <td className="py-3.5 px-4 font-mono text-[11px]">
                            {(() => {
                              if (model.model_family === 'baseline') {
                                return (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 font-semibold">
                                    Baseline
                                  </span>
                                );
                              }
                              const baseComp = model.evaluation_summary?.baseline_comparison;
                              if (!baseComp || baseComp.beats_baseline === undefined) {
                                return <span className="text-slate-400">—</span>;
                              }
                              const absImp = baseComp.absolute_improvement !== undefined && baseComp.absolute_improvement !== null
                                ? Number(baseComp.absolute_improvement).toFixed(4)
                                : (baseComp.improvement !== undefined ? Number(baseComp.improvement).toFixed(4) : null);
                              const impPct = baseComp.improvement_pct !== undefined && baseComp.improvement_pct !== null
                                ? `${Number(baseComp.improvement_pct) > 0 ? '+' : ''}${Number(baseComp.improvement_pct).toFixed(2)}%`
                                : null;

                              if (baseComp.beats_baseline) {
                                return (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60 font-bold whitespace-nowrap">
                                    <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600 flex-shrink-0" />
                                    {absImp !== null ? `+${absImp}` : 'Outperforms'} {impPct ? `(${impPct})` : ''}
                                  </span>
                                );
                              } else {
                                return (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60 font-bold whitespace-nowrap">
                                    <AlertTriangle className="w-3 h-3 mr-1 text-amber-500 flex-shrink-0" />
                                    {absImp !== null ? `${absImp}` : 'Underperforms'} {impPct ? `(${impPct})` : ''}
                                  </span>
                                );
                              }
                            })()}
                          </td>
                        )}
                        <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400">{model.training_duration_seconds}s</td>
                        <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400 font-mono">
                          {Math.round(model.artifact_size_bytes / 1024)} KB
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              model.status === 'SUCCESS'
                                ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300'
                                : 'bg-red-100 dark:bg-red-950/60 text-red-800 dark:text-red-300'
                            }`}
                          >
                            {model.status}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                          {model.is_active ? (
                            <span className="inline-flex items-center text-emerald-600 dark:text-emerald-400 font-bold text-xs">
                              <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Champion
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleActivateModel(model.id)}
                              disabled={activatingId === model.id || model.status !== 'SUCCESS'}
                              className="px-3 py-1 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold transition-all shadow-2xs disabled:opacity-50"
                            >
                              {activatingId === model.id ? 'Deploying...' : 'Promote to Active'}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Visual Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Metric Comparison Chart */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-sm transition-colors">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Candidate Comparison ({comparison.primary_metric.toUpperCase()})
                  </h4>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    Lower is better for regression/forecasting; higher is better for classification.
                  </p>
                </div>
                <BarChart2 className="w-4 h-4 text-slate-400" />
              </div>

              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metricChartData} margin={{ top: 10, right: 10, left: -10, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? '#334155' : '#f1f5f9'} />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                      stroke={isDark ? '#475569' : '#cbd5e1'}
                      angle={-15}
                      textAnchor="end"
                      interval={0}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                      stroke={isDark ? '#475569' : '#cbd5e1'}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: isDark ? '#1e293b' : '#ffffff',
                        borderColor: isDark ? '#334155' : '#e2e8f0',
                        color: isDark ? '#f8fafc' : '#0f172a',
                        fontSize: 12,
                        borderRadius: 8,
                        boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                      }}
                      itemStyle={{ color: isDark ? '#f8fafc' : '#0f172a' }}
                    />
                    <Bar
                      dataKey={comparison.primary_metric.toUpperCase()}
                      fill="#6366f1"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Selected Model: Actual vs Predicted */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-sm transition-colors">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Actual vs. Predicted: {selectedModel?.algorithm_display_name}
                  </h4>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    Validation holdout points comparison (first 30 instances).
                  </p>
                </div>
                <TrendingUp className="w-4 h-4 text-slate-400" />
              </div>

              <div className="h-64">
                {samplePredChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={samplePredChartData} margin={{ top: 10, right: 10, left: -10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? '#334155' : '#f1f5f9'} />
                      <XAxis
                        dataKey="index"
                        tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                        stroke={isDark ? '#475569' : '#cbd5e1'}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                        stroke={isDark ? '#475569' : '#cbd5e1'}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: isDark ? '#1e293b' : '#ffffff',
                          borderColor: isDark ? '#334155' : '#e2e8f0',
                          color: isDark ? '#f8fafc' : '#0f172a',
                          fontSize: 12,
                          borderRadius: 8,
                          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                        }}
                        itemStyle={{ color: isDark ? '#f8fafc' : '#0f172a' }}
                      />
                      <Legend wrapperStyle={{ fontSize: 11, color: isDark ? '#94a3b8' : '#64748b' }} />
                      <Line
                        type="monotone"
                        dataKey="Actual"
                        stroke={isDark ? '#e2e8f0' : '#0f172a'}
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="Predicted"
                        stroke="#6366f1"
                        strokeWidth={2}
                        strokeDasharray="4 4"
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-400 text-xs">
                    No holdout validation sample points available for this model.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Feature Importance & Hyperparameters Strip */}
          {selectedModel && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Feature Importance */}
              <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-sm transition-colors">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                      Predictor Importance: {selectedModel.algorithm_display_name}
                    </h4>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">Relative contribution percentage of each feature.</p>
                  </div>
                  <Zap className="w-4 h-4 text-amber-500" />
                </div>

                {featureImpData.length > 0 ? (
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={featureImpData} layout="vertical" margin={{ top: 5, right: 20, left: 40, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={isDark ? '#334155' : '#f1f5f9'} />
                        <XAxis
                          type="number"
                          tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                          stroke={isDark ? '#475569' : '#cbd5e1'}
                          unit="%"
                        />
                        <YAxis
                          dataKey="feature"
                          type="category"
                          tick={{ fontSize: 10, fill: isDark ? '#94a3b8' : '#64748b' }}
                          stroke={isDark ? '#475569' : '#cbd5e1'}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: isDark ? '#1e293b' : '#ffffff',
                            borderColor: isDark ? '#334155' : '#e2e8f0',
                            color: isDark ? '#f8fafc' : '#0f172a',
                            fontSize: 12,
                            borderRadius: 8,
                            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                          }}
                          itemStyle={{ color: isDark ? '#f8fafc' : '#0f172a' }}
                        />
                        <Bar dataKey="importance" fill="#818cf8" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-56 flex items-center justify-center text-slate-400 text-xs italic">
                    Feature importances not applicable for this baseline algorithm.
                  </div>
                )}
              </div>

              {/* Model Specifications & Hyperparameters */}
              <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-sm flex flex-col justify-between transition-colors">
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 mb-3">Model Specifications</h4>
                  <div className="space-y-2.5 text-xs">
                    <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                      <span className="text-slate-500 dark:text-slate-400">Algorithm</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">{selectedModel.algorithm}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                      <span className="text-slate-500 dark:text-slate-400">Family</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200 uppercase">{selectedModel.model_family}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                      <span className="text-slate-500 dark:text-slate-400">Artifact Size</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">
                        {Math.round(selectedModel.artifact_size_bytes / 1024)} KB
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                      <span className="text-slate-500 dark:text-slate-400">Fit Duration</span>
                      <span className="font-semibold text-slate-800 dark:text-slate-200">{selectedModel.training_duration_seconds}s</span>
                    </div>
                  </div>

                  <div className="mt-4">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                      Hyperparameters
                    </span>
                    <pre className="bg-slate-50 dark:bg-slate-950 p-2.5 rounded-lg text-[11px] font-mono text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 overflow-x-auto max-h-28">
                      {JSON.stringify(selectedModel.hyperparameters || {}, null, 2)}
                    </pre>
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 mt-4">
                  <button
                    type="button"
                    onClick={() => navigate(`/predictions?model_id=${selectedModel.id}`)}
                    className="w-full inline-flex items-center justify-center space-x-2 py-2 bg-slate-900 dark:bg-brand-600 hover:bg-slate-800 dark:hover:bg-brand-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm"
                  >
                    <span>Test in Prediction Engine</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Evidence-Based Performance Diagnosis & Baseline Benchmark Panel */}
          {selectedModel && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-sm transition-colors space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800 gap-2">
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                    <Activity className="w-4 h-4 text-brand-600 dark:text-brand-400" />
                    <span>Evidence-Based Model Diagnosis: {selectedModel.algorithm_display_name}</span>
                  </h4>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    Rigorous holdout evaluation benchmarks, baseline deltas, and training-versus-validation diagnostics.
                  </p>
                </div>
                {selectedModel.model_family !== 'baseline' && (
                  <div>
                    {selectedModel.evaluation_summary?.baseline_comparison?.beats_baseline ? (
                      <span className="px-3 py-1 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 rounded-lg text-xs font-bold inline-flex items-center">
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" /> Outperforms Baseline
                      </span>
                    ) : (
                      <span className="px-3 py-1 bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 rounded-lg text-xs font-bold inline-flex items-center">
                        <AlertTriangle className="w-3.5 h-3.5 mr-1 text-amber-600" /> Underperforms Baseline
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Metric Breakdown Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Primary Validation Metric</span>
                  <span className="text-base font-extrabold font-mono text-slate-900 dark:text-slate-100">
                    {selectedModel.metrics?.[comparison.primary_metric] !== undefined
                      ? Number(selectedModel.metrics[comparison.primary_metric]).toFixed(4)
                      : '--'}
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">{comparison.primary_metric.toUpperCase()}</span>
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Baseline Benchmark</span>
                  <span className="text-base font-extrabold font-mono text-slate-900 dark:text-slate-100">
                    {selectedModel.evaluation_summary?.baseline_comparison?.baseline_value !== undefined
                      ? Number(selectedModel.evaluation_summary.baseline_comparison.baseline_value).toFixed(4)
                      : '--'}
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">Reference Baseline</span>
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Absolute Delta</span>
                  <span className={`text-base font-extrabold font-mono ${
                    selectedModel.evaluation_summary?.baseline_comparison?.beats_baseline
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-amber-600 dark:text-amber-400'
                  }`}>
                    {selectedModel.evaluation_summary?.baseline_comparison?.absolute_improvement !== undefined
                      ? (Number(selectedModel.evaluation_summary.baseline_comparison.absolute_improvement) >= 0 ? '+' : '') +
                        Number(selectedModel.evaluation_summary.baseline_comparison.absolute_improvement).toFixed(4)
                      : (selectedModel.evaluation_summary?.baseline_comparison?.improvement !== undefined
                          ? (Number(selectedModel.evaluation_summary.baseline_comparison.improvement) >= 0 ? '+' : '') +
                            Number(selectedModel.evaluation_summary.baseline_comparison.improvement).toFixed(4)
                          : '--')}
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">Error / F1 Delta</span>
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Relative Improvement</span>
                  <span className={`text-base font-extrabold font-mono ${
                    selectedModel.evaluation_summary?.baseline_comparison?.beats_baseline
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-amber-600 dark:text-amber-400'
                  }`}>
                    {selectedModel.evaluation_summary?.baseline_comparison?.improvement_pct !== undefined
                      ? (Number(selectedModel.evaluation_summary.baseline_comparison.improvement_pct) >= 0 ? '+' : '') +
                        Number(selectedModel.evaluation_summary.baseline_comparison.improvement_pct).toFixed(2) + '%'
                      : '--'}
                  </span>
                  <span className="text-[10px] text-slate-500 block mt-0.5 font-mono">Vs. Reference Baseline</span>
                </div>
              </div>

              {/* Factual Performance Explanation Callout */}
              {(selectedModel.evaluation_summary?.performance_explanation ||
                (selectedModel.evaluation_summary?.warnings && selectedModel.evaluation_summary.warnings.length > 0)) && (
                <div className="p-4 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700/80 space-y-2">
                  <span className="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center space-x-1.5">
                    <Info className="w-3.5 h-3.5 text-blue-500" />
                    <span>Evidence-Based Diagnostic Analysis</span>
                  </span>
                  {selectedModel.evaluation_summary?.performance_explanation && (
                    <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-sans">
                      {selectedModel.evaluation_summary.performance_explanation}
                    </p>
                  )}
                  {selectedModel.evaluation_summary?.warnings && selectedModel.evaluation_summary.warnings.map((w: string, i: number) => (
                    <div key={i} className="text-[11px] text-amber-700 dark:text-amber-300 flex items-start space-x-1.5 mt-1">
                      <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0 mt-0.5" />
                      <span>{w}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

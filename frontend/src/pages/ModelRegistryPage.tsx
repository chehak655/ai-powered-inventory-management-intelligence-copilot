import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { modelsApi } from '../services/api';
import { CandidateModel, ModelSchemaResponse } from '../types';
import {
  Layers,
  CheckCircle2,
  Cpu,
  Sparkles,
  ArrowRight,
  Code2,
  X,
  Filter,
  Check,
} from 'lucide-react';

export const ModelRegistryPage: React.FC = () => {
  const navigate = useNavigate();
  const [models, setModels] = useState<CandidateModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterActive, setFilterActive] = useState<boolean | undefined>(undefined);
  const [selectedSchema, setSelectedSchema] = useState<ModelSchemaResponse | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchModels = async () => {
    setLoading(true);
    try {
      const data = await modelsApi.list(undefined, filterActive);
      setModels(data);
    } catch (err) {
      console.error('Failed to load models:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, [filterActive]);

  // Close schema modal on Escape key press
  useEffect(() => {
    if (!selectedSchema) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedSchema(null);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedSchema]);

  // Lock body scroll while modal open
  useEffect(() => {
    if (!selectedSchema) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [selectedSchema]);

  const handleActivate = async (id: string) => {
    const targetModel = models.find((m) => m.id === id);
    const baselineComp = targetModel?.evaluation_summary?.baseline_comparison;
    const beatsBaseline = baselineComp?.beats_baseline;

    if (beatsBaseline === false) {
      const metricName = baselineComp?.primary_metric?.toUpperCase() || 'PRIMARY METRIC';
      const candVal = baselineComp?.candidate_value ?? targetModel?.metrics?.mae ?? targetModel?.metrics?.rmse ?? targetModel?.metrics?.macro_f1;
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
        `This will replace any currently active model for this dataset.`
      );
      if (!proceed) return;
    }

    setActivatingId(id);
    setSuccessMsg(null);
    try {
      await modelsApi.activate(id);
      setSuccessMsg('Model promoted to active status.');
      fetchModels();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to activate model.');
    } finally {
      setActivatingId(null);
    }
  };

  const handleViewSchema = async (id: string) => {
    setSchemaLoading(true);
    try {
      const schema = await modelsApi.getSchema(id);
      setSelectedSchema(schema);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to fetch schema.');
    } finally {
      setSchemaLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-200/80 dark:border-slate-800 gap-4">
        <div>
          <div className="flex items-center space-x-2 text-brand-600 dark:text-brand-400 text-xs font-bold uppercase tracking-wider">
            <Layers className="w-4 h-4" />
            <span>Phase E • Production Model Management</span>
          </div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-slate-100 tracking-tight mt-1">Model Registry</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Browse registered candidate and champion models, inspect input feature schemas, and govern production deployments.
          </p>
        </div>

        {/* Filter controls */}
        <div className="flex items-center space-x-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <button
            onClick={() => setFilterActive(undefined)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              filterActive === undefined
                ? 'bg-slate-900 dark:bg-brand-600 text-white'
                : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
            }`}
          >
            All Models
          </button>
          <button
            onClick={() => setFilterActive(true)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              filterActive === true
                ? 'bg-emerald-600 text-white'
                : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
            }`}
          >
            Active Champion Models
          </button>
        </div>
      </div>

      {successMsg && (
        <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center space-x-2">
          <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          <span>{successMsg}</span>
        </div>
      )}

      {loading ? (
        <div className="p-16 text-center text-slate-400 text-sm">Loading model registry catalog...</div>
      ) : models.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-12 text-center max-w-md mx-auto shadow-sm">
          <Layers className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800 dark:text-slate-200">No Models in Registry</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Train machine learning candidate algorithms from your uploaded datasets to register models.
          </p>
          <button
            onClick={() => navigate('/datasets')}
            className="mt-4 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm"
          >
            Go to Datasets
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {models.map((m) => {
            const metrics = m.metrics || {};
            let metricLabel = 'Metric';
            let metricValue = '--';

            if (m.model_family === 'anomaly') {
              metricLabel = 'Anomaly Rate';
              if (metrics.observed_anomaly_pct !== undefined) {
                metricValue = `${metrics.observed_anomaly_pct}%`;
              } else if (metrics.contamination_rate !== undefined) {
                const r = Number(metrics.contamination_rate);
                metricValue = `${(r <= 1.0 ? r * 100 : r).toFixed(2)}%`;
              }
            } else if (metrics.macro_f1 !== undefined) {
              metricLabel = 'Macro F1';
              metricValue = Number(metrics.macro_f1).toFixed(4);
            } else if (metrics.rmse !== undefined) {
              metricLabel = 'RMSE';
              metricValue = Number(metrics.rmse).toFixed(4);
            } else if (metrics.mae !== undefined) {
              metricLabel = 'MAE';
              metricValue = Number(metrics.mae).toFixed(4);
            } else if (metrics.f1 !== undefined) {
              metricLabel = 'Macro F1';
              metricValue = Number(metrics.f1).toFixed(4);
            } else if (metrics.accuracy !== undefined) {
              metricLabel = 'Accuracy';
              metricValue = `${(Number(metrics.accuracy) * 100).toFixed(1)}%`;
            } else {
              const k = Object.keys(metrics)[0] || 'score';
              metricLabel = k.toUpperCase();
              metricValue = metrics[k] !== undefined ? String(metrics[k]) : '--';
            }

            return (
              <div
                key={m.id}
                className={`bg-white dark:bg-slate-900 rounded-2xl border p-5 shadow-sm transition-all hover:shadow-md flex flex-col justify-between ${
                  m.is_active
                    ? 'border-emerald-300 dark:border-emerald-500/50 ring-2 ring-emerald-100 dark:ring-emerald-950/40'
                    : 'border-slate-200/80 dark:border-slate-800'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                      {m.model_family}
                    </span>
                    {m.is_active ? (
                      <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Active Production</span>
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500">Standby Candidate</span>
                    )}
                  </div>

                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 leading-tight">
                    {m.algorithm_display_name}
                  </h3>
                  <div className="text-[11px] font-mono text-slate-400 dark:text-slate-500 mt-1">
                    ID: {m.id.slice(0, 8)}...
                  </div>

                  {/* Primary Metrics */}
                  <div className="mt-4 p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase block">
                        {metricLabel}
                      </span>
                      <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                        {metricValue}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase block">Artifact</span>
                      <span className="font-mono text-slate-700 dark:text-slate-300">
                        {Math.round(m.artifact_size_bytes / 1024)} KB
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
                  <button
                    onClick={() => handleViewSchema(m.id)}
                    className="inline-flex items-center space-x-1 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 text-xs font-semibold"
                  >
                    <Code2 className="w-3.5 h-3.5" />
                    <span>Schema</span>
                  </button>

                  <div className="flex items-center space-x-2">
                    {!m.is_active && m.status === 'SUCCESS' && (
                      <button
                        onClick={() => handleActivate(m.id)}
                        disabled={activatingId === m.id}
                        className="px-2.5 py-1 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/50 rounded-lg transition-colors"
                      >
                        {activatingId === m.id ? 'Deploying...' : 'Activate'}
                      </button>
                    )}

                    <button
                      onClick={() => navigate(`/predictions?model_id=${m.id}`)}
                      className="inline-flex items-center space-x-1 px-3 py-1.5 bg-slate-900 dark:bg-brand-600 hover:bg-slate-800 dark:hover:bg-brand-700 text-white rounded-lg text-xs font-bold transition-all shadow-2xs"
                    >
                      <span>Predict</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Schema Inspection Modal */}
      {selectedSchema &&
        createPortal(
          <div
            className="fixed inset-0 m-0 p-4 sm:p-6 z-50 bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm flex items-center justify-center overflow-y-auto transition-opacity duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget) setSelectedSchema(null);
            }}
            role="dialog"
            aria-modal="true"
          >
            <div
              className="relative bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-4 transition-colors max-h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-3rem)] overflow-y-auto my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Input Feature Schema</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Required fields for {selectedSchema.algorithm_display_name}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedSchema(null)}
                  className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  aria-label="Close schema dialog"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {selectedSchema.fields.map((f) => (
                  <div key={f.name} className="p-2.5 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-slate-800 dark:text-slate-200">{f.name}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 uppercase font-semibold">
                        {f.type}
                      </span>
                    </div>
                    {f.sample_values && f.sample_values.length > 0 && (
                      <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                        Samples: <span className="font-mono text-slate-700 dark:text-slate-300">{f.sample_values.slice(0, 3).join(', ')}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex justify-end">
                <button
                  type="button"
                  onClick={() => setSelectedSchema(null)}
                  className="px-4 py-2 bg-slate-900 dark:bg-slate-800 hover:bg-slate-800 dark:hover:bg-slate-700 text-white rounded-lg text-xs font-semibold transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
};

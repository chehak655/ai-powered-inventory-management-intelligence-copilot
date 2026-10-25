import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { modelsApi, predictionApi } from '../services/api';
import { CandidateModel, ModelSchemaResponse, PredictionResponse, PredictionLog } from '../types';
import {
  Sparkles,
  Zap,
  Upload,
  Download,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Play,
  FileSpreadsheet,
  History,
  RotateCw,
} from 'lucide-react';

export const PredictionsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const urlModelId = searchParams.get('model_id');

  const [activeTab, setActiveTab] = useState<'single' | 'batch' | 'history'>('single');
  const [models, setModels] = useState<CandidateModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>(urlModelId || '');
  const [schema, setSchema] = useState<ModelSchemaResponse | null>(null);

  // Single Prediction Form State
  const [formInputs, setFormInputs] = useState<Record<string, any>>({});
  const [singlePredicting, setSinglePredicting] = useState(false);
  const [singleResult, setSingleResult] = useState<PredictionResponse | null>(null);
  const [singleError, setSingleError] = useState<string | null>(null);

  // Batch CSV State
  const [batchFile, setBatchFile] = useState<File | null>(null);
  const [batchPredicting, setBatchPredicting] = useState(false);
  const [batchSuccess, setBatchSuccess] = useState<string | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);

  // History State
  const [historyLogs, setHistoryLogs] = useState<PredictionLog[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // 1. Fetch available models
  useEffect(() => {
    modelsApi.list().then((list) => {
      setModels(list);
      if (list.length > 0) {
        if (!selectedModelId) {
          const active = list.find((m) => m.is_active) || list[0];
          setSelectedModelId(active.id);
        }
      }
    });
  }, []);

  // 2. Fetch schema whenever selected model changes
  useEffect(() => {
    if (!selectedModelId) return;
    modelsApi
      .getSchema(selectedModelId)
      .then((res) => {
        setSchema(res);
        // Pre-fill inputs with default/sample values
        const defaults: Record<string, any> = {};
        res.fields.forEach((f) => {
          defaults[f.name] = f.default !== undefined && f.default !== null ? f.default : '';
        });
        setFormInputs(defaults);
        setSingleResult(null);
        setSingleError(null);
      })
      .catch((err) => {
        console.error('Failed to load model schema:', err);
      });
  }, [selectedModelId]);

  // 3. Fetch history when history tab opens
  const fetchHistory = async () => {
    setHistoryLoading(true);
    try {
      const logs = await predictionApi.getHistory(selectedModelId || undefined);
      setHistoryLogs(logs);
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab, selectedModelId]);

  const handleSingleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModelId) return;
    setSinglePredicting(true);
    setSingleError(null);

    // Cast numeric types where applicable
    const payloadInputs: Record<string, any> = {};
    if (schema) {
      schema.fields.forEach((f) => {
        const raw = formInputs[f.name];
        if (f.type === 'numeric') {
          payloadInputs[f.name] = raw === '' ? 0 : Number(raw);
        } else {
          payloadInputs[f.name] = raw;
        }
      });
    }

    try {
      const res = await predictionApi.predictSingle({
        model_id: selectedModelId,
        inputs: payloadInputs,
      });
      setSingleResult(res);
    } catch (err: any) {
      setSingleError(err.response?.data?.detail || 'Inference execution failed.');
    } finally {
      setSinglePredicting(false);
    }
  };

  const handleBatchFileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!batchFile || !selectedModelId) return;
    setBatchPredicting(true);
    setBatchSuccess(null);
    setBatchError(null);

    try {
      const blob = await predictionApi.predictBatchFile(batchFile, selectedModelId);
      // Trigger automatic file download
      const url = window.URL.createObjectURL(new Blob([blob], { type: 'text/csv' }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `predicted_${batchFile.name}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setBatchSuccess(`Predictions generated successfully! Downloaded enriched CSV.`);
    } catch (err: any) {
      setBatchError(err.response?.data?.detail || 'Batch prediction failed.');
    } finally {
      setBatchPredicting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-200/80 dark:border-slate-800 gap-4">
        <div>
          <div className="flex items-center space-x-2 text-brand-600 dark:text-brand-400 text-xs font-bold uppercase tracking-wider">
            <Sparkles className="w-4 h-4" />
            <span>Phase E • Low-Latency Model Inference</span>
          </div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-slate-100 tracking-tight mt-1">Predictions Engine</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Generate real-time predictions, run batch CSV inferences, and inspect audit logs using trained pipeline artifacts.
          </p>
        </div>

        {/* Model Selection Dropdown */}
        <div className="min-w-64">
          <label className="block text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">
            Active Prediction Model
          </label>
          <select
            value={selectedModelId}
            onChange={(e) => setSelectedModelId(e.target.value)}
            className="w-full bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-xs font-semibold px-3 py-2 text-slate-800 dark:text-slate-200 focus:ring-brand-500 focus:border-brand-500"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.algorithm_display_name} {m.is_active ? '★ (Active)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 dark:border-slate-800 gap-6">
        <button
          onClick={() => setActiveTab('single')}
          className={`pb-3 text-xs font-bold transition-all relative ${
            activeTab === 'single'
              ? 'text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-600 dark:border-indigo-400'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          Single Record Inference
        </button>
        <button
          onClick={() => setActiveTab('batch')}
          className={`pb-3 text-xs font-bold transition-all relative ${
            activeTab === 'batch'
              ? 'text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-600 dark:border-indigo-400'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          Batch CSV Prediction
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`pb-3 text-xs font-bold transition-all relative ${
            activeTab === 'history'
              ? 'text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-600 dark:border-indigo-400'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          Inference Logs & History
        </button>
      </div>

      {/* TAB 1: SINGLE RECORD PREDICTION */}
      {activeTab === 'single' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Dynamic Form */}
          <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-6 shadow-sm transition-colors">
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-1">Input Feature Values</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-6">
              Enter predictor values matching the model schema. Required fields are dynamically validated.
            </p>

            {singleError && (
              <div className="mb-4 p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 rounded-xl text-xs flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
                <span>{singleError}</span>
              </div>
            )}

            {!schema ? (
              <div className="p-8 text-center text-slate-400 text-xs">Loading model schema inputs...</div>
            ) : (
              <form onSubmit={handleSingleSubmit} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {schema.fields.map((field) => (
                    <div key={field.name}>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-bold font-mono text-slate-700 dark:text-slate-300">{field.name}</label>
                        <span className="text-[10px] uppercase font-semibold text-slate-400 dark:text-slate-500">{field.type}</span>
                      </div>
                      <input
                        type={field.type === 'numeric' ? 'number' : 'text'}
                        step={field.type === 'numeric' ? 'any' : undefined}
                        value={formInputs[field.name] ?? ''}
                        onChange={(e) =>
                          setFormInputs({
                            ...formInputs,
                            [field.name]: e.target.value,
                          })
                        }
                        placeholder={
                          field.sample_values?.length ? `e.g. ${field.sample_values[0]}` : `Enter ${field.name}`
                        }
                        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-xs font-medium text-slate-900 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:ring-brand-500 focus:border-brand-500"
                      />
                    </div>
                  ))}
                </div>

                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex justify-end">
                  <button
                    type="submit"
                    disabled={singlePredicting}
                    className="inline-flex items-center space-x-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm disabled:opacity-50"
                  >
                    {singlePredicting ? (
                      <>
                        <RotateCw className="w-4 h-4 animate-spin" />
                        <span>Computing Prediction...</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 fill-current" />
                        <span>Generate Prediction</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>

          {/* Result Card */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-6 shadow-sm flex flex-col justify-between transition-colors">
            <div>
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">Prediction Output</h4>
                {singleResult && (
                  <span className="inline-flex items-center space-x-1 text-[11px] font-mono text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                    <Clock className="w-3 h-3 text-slate-400" />
                    <span>{singleResult.latency_ms} ms</span>
                  </span>
                )}
              </div>

              {singleResult ? (
                <div className="space-y-4">
                  <div className="p-4 bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-800/60 rounded-xl text-center">
                    <span className="text-[10px] uppercase font-bold text-indigo-600 dark:text-indigo-400 tracking-wider block">
                      Target Estimate ({schema?.target_column || 'Prediction'})
                    </span>
                    <div className="text-3xl font-black text-indigo-950 dark:text-indigo-200 font-mono mt-1">
                      {typeof singleResult.predictions[0]?.prediction === 'number'
                        ? Number(singleResult.predictions[0].prediction).toFixed(2)
                        : String(singleResult.predictions[0]?.prediction)}
                    </div>
                  </div>

                  {singleResult.predictions[0]?.probabilities && (
                    <div>
                      <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-2">Class Confidence</span>
                      <div className="space-y-1.5">
                        {singleResult.predictions[0].probabilities.map((prob, i) => {
                          const label = singleResult.classes ? singleResult.classes[i] : `Class ${i}`;
                          return (
                            <div key={label} className="text-xs">
                              <div className="flex justify-between text-slate-600 dark:text-slate-400 mb-0.5">
                                <span className="font-semibold">{label}</span>
                                <span className="font-mono">{(prob * 100).toFixed(1)}%</span>
                              </div>
                              <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className="bg-indigo-600 h-1.5 rounded-full"
                                  style={{ width: `${prob * 100}%` }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800 text-[11px] text-slate-600 dark:text-slate-400 space-y-1">
                    <div className="flex justify-between">
                      <span>Model Used:</span>
                      <span className="font-bold text-slate-800 dark:text-slate-200">{singleResult.algorithm_display_name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Prediction ID:</span>
                      <span className="font-mono text-slate-500 dark:text-slate-400">{singleResult.prediction_id.slice(0, 8)}...</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-slate-400 text-xs italic">
                  Fill in the input features and click "Generate Prediction" to compute real-time inference.
                </div>
              )}
            </div>

            <div className="p-3 bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-900/50 rounded-xl text-[11px] text-amber-800 dark:text-amber-300 flex items-start space-x-2 mt-6">
              <Zap className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <span>
                Predictions run through the serialised scikit-learn/XGBoost preprocessing pipeline with missing-value imputers.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: BATCH CSV INFERENCE */}
      {activeTab === 'batch' && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-8 shadow-sm max-w-2xl mx-auto space-y-6 transition-colors">
          <div className="text-center">
            <FileSpreadsheet className="w-12 h-12 text-indigo-500 mx-auto mb-2" />
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Batch Dataset Inference</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto mt-1">
              Upload a test CSV or XLSX containing feature columns. We will run pipeline inference and stream back an enriched CSV with predicted values.
            </p>
          </div>

          {batchSuccess && (
            <div className="p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 rounded-xl text-xs flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
              <span>{batchSuccess}</span>
            </div>
          )}

          {batchError && (
            <div className="p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 rounded-xl text-xs flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <span>{batchError}</span>
            </div>
          )}

          <form onSubmit={handleBatchFileSubmit} className="space-y-4">
            <div className="border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-xl p-6 text-center hover:border-indigo-400 dark:hover:border-indigo-500 transition-colors">
              <input
                type="file"
                accept=".csv,.xlsx"
                id="batch-file-input"
                onChange={(e) => setBatchFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              <label htmlFor="batch-file-input" className="cursor-pointer space-y-2 block">
                <Upload className="w-8 h-8 text-slate-400 mx-auto" />
                <div className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {batchFile ? batchFile.name : 'Click to select CSV or Excel dataset'}
                </div>
                <div className="text-[10px] text-slate-400 dark:text-slate-500">Supports .csv and .xlsx up to 50MB</div>
              </label>
            </div>

            <button
              type="submit"
              disabled={!batchFile || batchPredicting}
              className="w-full inline-flex items-center justify-center space-x-2 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm disabled:opacity-50"
            >
              {batchPredicting ? (
                <>
                  <RotateCw className="w-4 h-4 animate-spin" />
                  <span>Processing Batch Predictions...</span>
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  <span>Run Batch Inference & Download CSV</span>
                </>
              )}
            </button>
          </form>
        </div>
      )}

      {/* TAB 3: INFERENCE LOGS & HISTORY */}
      {activeTab === 'history' && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden shadow-sm transition-colors">
          <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">Prediction Query History</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Audit log of real-time and batch inferences executed in workspace.</p>
            </div>
            <button
              onClick={fetchHistory}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <RotateCw className="w-4 h-4" />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 font-semibold uppercase">
                  <th className="py-2.5 px-4">Log ID</th>
                  <th className="py-2.5 px-4">Type</th>
                  <th className="py-2.5 px-4">Rows</th>
                  <th className="py-2.5 px-4">Latency</th>
                  <th className="py-2.5 px-4">Input Preview</th>
                  <th className="py-2.5 px-4">Output Preview</th>
                  <th className="py-2.5 px-4 text-right">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {historyLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600 dark:text-slate-400">{log.id.slice(0, 8)}...</td>
                    <td className="py-3 px-4 uppercase font-bold text-[10px] text-slate-700 dark:text-slate-300">
                      <span
                        className={`px-2 py-0.5 rounded-full ${
                          log.prediction_type === 'single'
                            ? 'bg-blue-100 dark:bg-blue-950/60 text-blue-800 dark:text-blue-300'
                            : 'bg-purple-100 dark:bg-purple-950/60 text-purple-800 dark:text-purple-300'
                        }`}
                      >
                        {log.prediction_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-700 dark:text-slate-300 font-semibold">{log.row_count} rows</td>
                    <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">{log.latency_ms} ms</td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-xs">
                      {JSON.stringify(log.input_sample || {})}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-800 dark:text-slate-200 truncate max-w-xs">
                      {JSON.stringify(log.output_sample || {})}
                    </td>
                    <td className="py-3 px-4 text-right text-slate-500 dark:text-slate-400">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

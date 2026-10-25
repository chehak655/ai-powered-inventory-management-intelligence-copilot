import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { datasetApi, trainingApi } from '../services/api';
import { Dataset, DatasetPreviewResponse, SuggestedConfig, DatasetConfiguration, TrainingRun } from '../types';
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Sliders,
  Table as TableIcon,
  Activity,
  Layers,
  Sparkles,
  Info,
  Calendar,
  Save,
  Check,
  Cpu,
  Play,
  Loader2,
  ExternalLink,
} from 'lucide-react';

export const DatasetDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'profiler' | 'preview' | 'config'>('profiler');

  // Preview state
  const [previewData, setPreviewData] = useState<DatasetPreviewResponse | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  const [previewPageSize, setPreviewPageSize] = useState(20);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Configuration state
  const [taskType, setTaskType] = useState<'regression' | 'forecasting' | 'classification' | 'anomaly'>('regression');
  const [targetColumn, setTargetColumn] = useState<string>('');
  const [dateColumn, setDateColumn] = useState<string>('');
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>([]);
  const [selectedEntities, setSelectedEntities] = useState<string[]>([]);
  const [configSaving, setConfigSaving] = useState(false);
  const [configSuccess, setConfigSuccess] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  // Training state
  const [trainingStarting, setTrainingStarting] = useState(false);
  const [trainingRuns, setTrainingRuns] = useState<TrainingRun[]>([]);
  const [activeRun, setActiveRun] = useState<TrainingRun | null>(null);
  const [trainingError, setTrainingError] = useState<string | null>(null);

  const clearMessages = () => {
    setConfigError(null);
    setTrainingError(null);
    setConfigSuccess(false);
  };

  const handleTaskTypeChange = (newTask: 'regression' | 'forecasting' | 'classification' | 'anomaly') => {
    setTaskType(newTask);
    clearMessages();

    // If switching to forecasting, ensure dateColumn is not in features or entities
    if (newTask === 'forecasting' && dateColumn) {
      setSelectedFeatures((prev) => prev.filter((f) => f !== dateColumn));
      setSelectedEntities((prev) => prev.filter((e) => e !== dateColumn));
    }
  };

  const handleTargetColumnChange = (newTarget: string) => {
    setTargetColumn(newTarget);
    clearMessages();

    if (newTarget) {
      setSelectedFeatures((prev) => prev.filter((f) => f !== newTarget));
      setSelectedEntities((prev) => prev.filter((e) => e !== newTarget));
    }
  };

  const handleDateColumnChange = (newDate: string) => {
    setDateColumn(newDate);
    clearMessages();

    if (newDate) {
      // Remove newly selected date from regular features and entities
      setSelectedFeatures((prev) => prev.filter((f) => f !== newDate));
      setSelectedEntities((prev) => prev.filter((e) => e !== newDate));
    }
  };

  const fetchTrainingRuns = async () => {
    if (!id) return;
    try {
      const runs = await trainingApi.listRuns(id);
      setTrainingRuns(runs);
      if (runs.length > 0 && (runs[0].status === 'QUEUED' || runs[0].status === 'RUNNING')) {
        setActiveRun(runs[0]);
      } else if (runs.length > 0 && !activeRun) {
        setActiveRun(runs[0]);
      }
    } catch (err) {
      console.error('Failed to load training runs:', err);
    }
  };

  const handleStartTraining = async () => {
    if (!id) return;
    setTrainingStarting(true);
    clearMessages();

    // Mutual exclusion: guarantee no date or target in feature columns or entities
    const normalizedFeatures = selectedFeatures.filter(
      (f) => f !== targetColumn && (taskType !== 'forecasting' || f !== dateColumn)
    );
    const normalizedEntities = selectedEntities.filter(
      (e) => e !== targetColumn && (taskType !== 'forecasting' || e !== dateColumn)
    );

    try {
      // Save configuration first
      await datasetApi.saveConfig(id, {
        task_type: taskType,
        target_column: taskType === 'anomaly' ? null : targetColumn || null,
        feature_columns: normalizedFeatures,
        date_column: taskType === 'forecasting' ? dateColumn || null : null,
        entity_columns: normalizedEntities.length > 0 ? normalizedEntities : null,
        excluded_columns: [],
      });
      setSelectedFeatures(normalizedFeatures);
      setSelectedEntities(normalizedEntities);
      setConfigSuccess(true);

      // Launch training run
      const run = await trainingApi.start(id, taskType);
      setActiveRun(run);
      await fetchTrainingRuns();
    } catch (err: any) {
      setConfigSuccess(false);
      setTrainingError(err.response?.data?.detail || 'Failed to start candidate model training.');
    } finally {
      setTrainingStarting(false);
    }
  };

  // Poll training status if run is active
  useEffect(() => {
    if (!activeRun || (activeRun.status !== 'QUEUED' && activeRun.status !== 'RUNNING')) return;

    const interval = setInterval(async () => {
      try {
        const statusRes = await trainingApi.getStatus(activeRun.id);
        if (['COMPLETED', 'FAILED', 'PARTIALLY_FAILED'].includes(statusRes.status)) {
          const fullRun = await trainingApi.getRun(activeRun.id);
          setActiveRun(fullRun);
          fetchTrainingRuns();
          clearInterval(interval);
        } else {
          setActiveRun((prev) =>
            prev ? { ...prev, status: statusRes.status as any, duration_seconds: statusRes.duration_seconds } : null
          );
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeRun?.id, activeRun?.status]);

  const fetchDatasetDetails = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await datasetApi.get(id);
      setDataset(data);
      await fetchTrainingRuns();

      // Check if existing configuration is saved
      try {
        const savedConfig = await datasetApi.getConfig(id);
        const sTask = savedConfig.task_type as any;
        const sTarget = savedConfig.target_column || '';
        const sDate = savedConfig.date_column || '';
        setTaskType(sTask);
        setTargetColumn(sTarget);
        setDateColumn(sDate);

        // Sanitize features so target and date (in forecasting) are never loaded into selectedFeatures
        const rawFeatures = savedConfig.feature_columns || [];
        const sanitizedFeatures = rawFeatures.filter(
          (f) => f !== sTarget && (sTask !== 'forecasting' || f !== sDate)
        );
        setSelectedFeatures(sanitizedFeatures);

        const rawEntities = savedConfig.entity_columns || [];
        const sanitizedEntities = rawEntities.filter(
          (e) => e !== sTarget && (sTask !== 'forecasting' || e !== sDate)
        );
        setSelectedEntities(sanitizedEntities);
      } catch {
        // If no saved config, load suggested defaults
        try {
          const sugg = await datasetApi.getSuggestedConfig(id);
          const suggTask = sugg.recommended_task as any;
          const suggTarget = sugg.target_column || '';
          const suggDate = sugg.date_column || '';
          setTaskType(suggTask);
          setTargetColumn(suggTarget);
          setDateColumn(suggDate);

          const rawFeatures = sugg.feature_columns || [];
          const sanitizedFeatures = rawFeatures.filter(
            (f) => f !== suggTarget && (suggTask !== 'forecasting' || f !== suggDate)
          );
          setSelectedFeatures(sanitizedFeatures);

          const rawEntities = sugg.entity_columns || [];
          const sanitizedEntities = rawEntities.filter(
            (e) => e !== suggTarget && (suggTask !== 'forecasting' || e !== suggDate)
          );
          setSelectedEntities(sanitizedEntities);
        } catch {}
      }
    } catch (err: any) {
      console.error('Failed to load dataset:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchPreview = async () => {
    if (!id) return;
    setPreviewLoading(true);
    try {
      const pdata = await datasetApi.preview(id, previewPage, previewPageSize);
      setPreviewData(pdata);
    } catch (err: any) {
      console.error('Failed to load preview:', err);
    } finally {
      setPreviewLoading(false);
    }
  };

  useEffect(() => {
    fetchDatasetDetails();
  }, [id]);

  useEffect(() => {
    if (activeTab === 'preview') {
      fetchPreview();
    }
  }, [id, activeTab, previewPage, previewPageSize]);

  const handleApplySuggestions = async () => {
    if (!id) return;
    clearMessages();
    try {
      const sugg = await datasetApi.getSuggestedConfig(id);
      const suggTask = sugg.recommended_task as any;
      const suggTarget = sugg.target_column || '';
      const suggDate = sugg.date_column || '';
      setTaskType(suggTask);
      setTargetColumn(suggTarget);
      setDateColumn(suggDate);

      const rawFeatures = sugg.feature_columns || [];
      const sanitizedFeatures = rawFeatures.filter(
        (f) => f !== suggTarget && (suggTask !== 'forecasting' || f !== suggDate)
      );
      setSelectedFeatures(sanitizedFeatures);

      const rawEntities = sugg.entity_columns || [];
      const sanitizedEntities = rawEntities.filter(
        (e) => e !== suggTarget && (suggTask !== 'forecasting' || e !== suggDate)
      );
      setSelectedEntities(sanitizedEntities);

      setConfigSuccess(true);
      setTimeout(() => setConfigSuccess(false), 3000);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;

    setConfigSaving(true);
    clearMessages();

    // Mutual exclusion: guarantee no date or target in feature columns or entities
    const normalizedFeatures = selectedFeatures.filter(
      (f) => f !== targetColumn && (taskType !== 'forecasting' || f !== dateColumn)
    );
    const normalizedEntities = selectedEntities.filter(
      (e) => e !== targetColumn && (taskType !== 'forecasting' || e !== dateColumn)
    );

    try {
      await datasetApi.saveConfig(id, {
        task_type: taskType,
        target_column: taskType === 'anomaly' ? null : targetColumn || null,
        feature_columns: normalizedFeatures,
        date_column: taskType === 'forecasting' ? dateColumn || null : null,
        entity_columns: normalizedEntities.length > 0 ? normalizedEntities : null,
        excluded_columns: [],
      });
      setSelectedFeatures(normalizedFeatures);
      setSelectedEntities(normalizedEntities);
      setConfigSuccess(true);
      setTimeout(() => setConfigSuccess(false), 4000);
    } catch (err: any) {
      setConfigSuccess(false);
      const msg = err.response?.data?.detail || err.message || 'Failed to save configuration.';
      setConfigError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setConfigSaving(false);
    }
  };

  const toggleFeature = (col: string) => {
    clearMessages();
    if (selectedFeatures.includes(col)) {
      setSelectedFeatures(selectedFeatures.filter((f) => f !== col));
    } else {
      setSelectedFeatures([...selectedFeatures, col]);
    }
  };

  const toggleEntity = (col: string) => {
    clearMessages();
    if (selectedEntities.includes(col)) {
      setSelectedEntities(selectedEntities.filter((e) => e !== col));
    } else {
      setSelectedEntities([...selectedEntities, col]);
    }
  };

  if (loading) {
    return (
      <div className="p-16 text-center text-slate-500">
        <Activity className="w-8 h-8 animate-spin text-brand-600 mx-auto mb-3" />
        <p className="text-sm">Inspecting dataset and loading profiling report...</p>
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="p-12 text-center">
        <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-2" />
        <h2 className="text-lg font-bold text-slate-800">Dataset not found</h2>
        <p className="text-sm text-slate-500 mt-1 mb-4">The requested dataset does not exist or access is restricted.</p>
        <button
          onClick={() => navigate('/datasets')}
          className="px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium"
        >
          Return to Datasets
        </button>
      </div>
    );
  }

  const profile = dataset.profile;
  const columns = profile?.columns || [];
  const allColumnNames = columns.map((c) => c.name);

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <button
            onClick={() => navigate('/datasets')}
            className="inline-flex items-center space-x-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 mb-2 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to All Datasets</span>
          </button>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">{dataset.name}</h1>
            <span className="text-xs uppercase px-2 py-0.5 rounded font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
              {dataset.file_format}
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            File: <span className="font-mono text-slate-700 dark:text-slate-300">{dataset.original_filename}</span> • {dataset.row_count.toLocaleString()} rows • {dataset.column_count} columns • Uploaded {new Date(dataset.created_at).toLocaleString()}
          </p>
        </div>

        {/* Tab Buttons */}
        <div className="flex bg-slate-100 dark:bg-slate-800 p-1 rounded-xl border border-slate-200 dark:border-slate-700">
          <button
            onClick={() => setActiveTab('profiler')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'profiler'
                ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Quality Profiler</span>
          </button>
          <button
            onClick={() => setActiveTab('preview')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'preview'
                ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>Data Preview</span>
          </button>
          <button
            onClick={() => setActiveTab('config')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'config'
                ? 'bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>Column Configuration</span>
          </button>
        </div>
      </div>

      {/* TAB 1: DATA QUALITY PROFILER */}
      {activeTab === 'profiler' && profile && (
        <div className="space-y-6">
          {/* KPI Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
              <div className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Dataset Health</div>
              <div className="flex items-center space-x-2 mt-2">
                <span className="text-2xl font-black text-slate-900 dark:text-slate-100">{profile.summary.health_score}%</span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                    profile.summary.health_score >= 80
                      ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300'
                      : 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300'
                  }`}
                >
                  {profile.summary.health_score >= 80 ? 'Optimal' : 'Needs Review'}
                </span>
              </div>
            </div>

            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
              <div className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Total Observations</div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">{profile.summary.row_count.toLocaleString()}</div>
            </div>

            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
              <div className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Total Features</div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">{profile.summary.column_count}</div>
            </div>

            <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
              <div className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Duplicate Rows</div>
              <div className="flex items-center space-x-2 mt-2">
                <span className="text-2xl font-black text-slate-900 dark:text-slate-100">{profile.summary.duplicate_rows}</span>
                <span className="text-xs text-slate-500 dark:text-slate-400">({profile.summary.duplicate_row_percentage}%)</span>
              </div>
            </div>
          </div>

          {/* Diagnostic Issues & Warnings */}
          {profile.issues && profile.issues.length > 0 && (
            <div className="bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 rounded-xl p-4 space-y-2">
              <div className="flex items-center space-x-2 text-amber-900 dark:text-amber-200 font-bold text-sm">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                <span>Data Quality Warnings ({profile.issues.length})</span>
              </div>
              <div className="space-y-1.5 pl-6 text-xs text-amber-800 dark:text-amber-300">
                {profile.issues.map((iss, i) => (
                  <div key={i} className="flex items-start space-x-2">
                    <span className="font-semibold text-amber-900 dark:text-amber-200">• {iss.column ? `[${iss.column}]` : '[Dataset]'}:</span>
                    <span>{iss.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Detailed Column Profiler Table */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden transition-colors">
            <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-sm text-slate-800 dark:text-slate-200">Column Schema & Profiling Summary</h3>
              <span className="text-xs text-slate-500 dark:text-slate-400">{columns.length} columns inspected</span>
            </div>

            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full text-left text-xs text-slate-700 dark:text-slate-300">
                <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-300 uppercase font-semibold">
                  <tr>
                    <th className="py-3 px-4">Column Name</th>
                    <th className="py-3 px-4">Inferred Type</th>
                    <th className="py-3 px-4">Missing Values</th>
                    <th className="py-3 px-4">Unique Values</th>
                    <th className="py-3 px-4">Diagnostic Flags</th>
                    <th className="py-3 px-4">Sample Values / Stats</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {columns.map((col) => (
                    <tr key={col.name} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                      <td className="py-3 px-4 font-bold text-slate-900 dark:text-slate-100 font-mono">{col.name}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase ${
                            col.inferred_type === 'numeric'
                              ? 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
                              : col.inferred_type === 'datetime'
                              ? 'bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800'
                              : col.inferred_type === 'boolean'
                              ? 'bg-teal-50 dark:bg-teal-950/40 text-teal-700 dark:text-teal-300 border border-teal-200 dark:border-teal-800'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          {col.inferred_type}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center space-x-2">
                          <span className={col.missing_percentage > 20 ? 'text-red-600 dark:text-red-400 font-bold' : ''}>
                            {col.missing_count} ({col.missing_percentage}%)
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-800 dark:text-slate-200 font-medium">
                        {col.unique_count.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 space-x-1">
                        {col.is_constant && (
                          <span className="px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950/50 text-red-700 dark:text-red-300 text-[10px] font-bold">
                            Constant
                          </span>
                        )}
                        {col.is_identifier && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/50 text-amber-800 dark:text-amber-300 text-[10px] font-bold">
                            Identifier
                          </span>
                        )}
                        {!col.is_constant && !col.is_identifier && (
                          <span className="text-slate-400 text-[11px]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-600 dark:text-slate-400 max-w-xs truncate">
                        {col.numeric_stats ? (
                          <span className="text-[11px] font-mono text-slate-700 dark:text-slate-300">
                            Min: {col.numeric_stats.min} | Mean: {col.numeric_stats.mean} | Max: {col.numeric_stats.max}
                          </span>
                        ) : col.datetime_stats ? (
                          <span className="text-[11px] font-mono text-slate-700 dark:text-slate-300">
                            Range: {col.datetime_stats.min_date.split('T')[0]} to {col.datetime_stats.max_date.split('T')[0]}
                          </span>
                        ) : (
                          <span>{col.sample_values?.slice(0, 3).join(', ')}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: DATA PREVIEW TABLE */}
      {activeTab === 'preview' && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden space-y-4 p-4 transition-colors">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
            <div className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              Paginated Raw Preview ({previewData?.total_rows.toLocaleString() || dataset.row_count} total records)
            </div>
            <div className="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400">
              <span>Page Size:</span>
              <select
                value={previewPageSize}
                onChange={(e) => {
                  setPreviewPageSize(Number(e.target.value));
                  setPreviewPage(1);
                }}
                className="border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded px-2 py-1 text-xs"
              >
                <option value={10}>10 rows</option>
                <option value={20}>20 rows</option>
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
              </select>
            </div>
          </div>

          {previewLoading ? (
            <div className="p-12 text-center text-slate-500 dark:text-slate-400 text-xs">Loading page records...</div>
          ) : previewData ? (
            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full text-left text-xs text-slate-700 dark:text-slate-300 border-collapse">
                <thead className="bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 uppercase font-semibold">
                  <tr>
                    <th className="py-2.5 px-3 border-b border-slate-200 dark:border-slate-700 text-slate-400 w-12">#</th>
                    {previewData.columns.map((col) => (
                      <th key={col} className="py-2.5 px-3 border-b border-slate-200 dark:border-slate-700 whitespace-nowrap font-mono">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono">
                  {previewData.records.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                      <td className="py-2 px-3 text-slate-400 text-[10px]">
                        {(previewPage - 1) * previewPageSize + idx + 1}
                      </td>
                      {previewData.columns.map((col) => (
                        <td key={col} className="py-2 px-3 text-slate-800 dark:text-slate-200 whitespace-nowrap">
                          {row[col] !== null ? String(row[col]) : <span className="text-slate-400 dark:text-slate-600 italic">null</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Preview Pagination */}
              <div className="pt-4 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>
                  Page {previewPage} of {previewData.total_pages}
                </span>
                <div className="space-x-1">
                  <button
                    disabled={previewPage <= 1}
                    onClick={() => setPreviewPage(previewPage - 1)}
                    className="px-3 py-1 border border-slate-200 dark:border-slate-700 rounded hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    disabled={previewPage >= previewData.total_pages}
                    onClick={() => setPreviewPage(previewPage + 1)}
                    className="px-3 py-1 border border-slate-200 dark:border-slate-700 rounded hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* TAB 3: DYNAMIC COLUMN CONFIGURATION WIZARD */}
      {activeTab === 'config' && (
        <div className="space-y-6">
          <form onSubmit={handleSaveConfig} className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-6 transition-colors">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800 gap-3">
              <div>
                <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">Configure Machine Learning Task & Columns</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Define target objectives, feature predictors, and grouping entities for downstream model training.
                </p>
              </div>

              <button
                type="button"
                onClick={handleApplySuggestions}
                className="inline-flex items-center space-x-1.5 px-3 py-2 bg-brand-50 dark:bg-blue-900/50 hover:bg-brand-100 dark:hover:bg-blue-800/60 text-brand-700 dark:text-blue-300 border border-transparent dark:border-blue-800/60 rounded-lg text-xs font-semibold transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Auto-Fill Recommendations</span>
              </button>
            </div>

            {/* Active Training Status Card */}
            {activeRun && (
              <div
                className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  activeRun.status === 'RUNNING' || activeRun.status === 'QUEUED'
                    ? 'bg-amber-50/70 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800/60 text-amber-900 dark:text-amber-200'
                    : activeRun.status === 'COMPLETED'
                    ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/60 text-emerald-900 dark:text-emerald-200'
                    : 'bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900/60 text-red-900 dark:text-red-200'
                }`}
              >
                <div className="flex items-center space-x-3">
                  {activeRun.status === 'RUNNING' || activeRun.status === 'QUEUED' ? (
                    <Loader2 className="w-5 h-5 text-amber-600 animate-spin flex-shrink-0" />
                  ) : activeRun.status === 'COMPLETED' ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                  ) : (
                    <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0" />
                  )}
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider">
                      Training Run: {activeRun.status} ({activeRun.task_type.toUpperCase()})
                    </div>
                    <div className="text-xs opacity-90 mt-0.5">
                      {activeRun.status === 'RUNNING' || activeRun.status === 'QUEUED'
                        ? `Training candidate algorithms in background... (${activeRun.duration_seconds}s elapsed)`
                        : activeRun.status === 'COMPLETED'
                        ? `Successfully trained ${activeRun.candidate_count} candidate models in ${activeRun.duration_seconds}s.`
                        : `Training failed: ${activeRun.error_message || 'Unknown error'}`}
                    </div>
                  </div>
                </div>

                {activeRun.status === 'COMPLETED' && (
                  <button
                    type="button"
                    onClick={() => navigate(`/models?run_id=${activeRun.id}&dataset_id=${id}`)}
                    className="inline-flex items-center space-x-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm"
                  >
                    <Cpu className="w-3.5 h-3.5" />
                    <span>Open in Model Lab</span>
                    <ExternalLink className="w-3 h-3 ml-0.5" />
                  </button>
                )}
              </div>
            )}

            {trainingError && (
              <div className="p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-xl text-xs text-red-700 dark:text-red-300 flex items-start space-x-2">
                <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <span>{trainingError}</span>
              </div>
            )}

            {configSuccess && !trainingError && !configError && (
              <div className="p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 rounded-xl text-xs text-emerald-800 dark:text-emerald-300 flex items-center space-x-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>Configuration successfully saved! Ready for candidate model training.</span>
              </div>
            )}

            {configError && (
              <div className="p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-xl text-xs text-red-700 dark:text-red-300 flex items-start space-x-2">
                <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <span>{configError}</span>
              </div>
            )}

            {/* Task Type Radio Selection Cards */}
            <div>
              <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2">
                1. Select Prediction Task
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  {
                    id: 'regression',
                    label: 'Regression',
                    desc: 'Predict continuous numeric variables (e.g. Sales, Revenue, Price).',
                  },
                  {
                    id: 'forecasting',
                    label: 'Demand Forecasting',
                    desc: 'Time-series forecasting with chronological lags & calendar signals.',
                  },
                  {
                    id: 'classification',
                    label: 'Classification',
                    desc: 'Predict categorical labels (e.g. Stockout Risk, Churn, Status).',
                  },
                  {
                    id: 'anomaly',
                    label: 'Anomaly Detection',
                    desc: 'Unsupervised outlier and inventory irregularity detection.',
                  },
                ].map((task) => (
                  <div
                    key={task.id}
                    onClick={() => handleTaskTypeChange(task.id as any)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                      taskType === task.id
                        ? 'border-brand-600 dark:border-blue-500 bg-brand-50/60 dark:bg-blue-950/40 ring-2 ring-brand-500/20'
                        : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/40'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-sm text-slate-900 dark:text-slate-100">{task.label}</span>
                      <input
                        type="radio"
                        name="task_type"
                        checked={taskType === task.id}
                        onChange={() => handleTaskTypeChange(task.id as any)}
                        className="text-brand-600 focus:ring-brand-500"
                      />
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{task.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Target Column Selector (Supervised) */}
            {taskType !== 'anomaly' && (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    2. Target Column (Dependent Variable)
                  </label>
                  <select
                    value={targetColumn}
                    onChange={(e) => handleTargetColumnChange(e.target.value)}
                    required
                    className="w-full sm:w-80 px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 font-mono focus:ring-2 focus:ring-brand-500 outline-none"
                  >
                    <option value="">-- Choose Target Column --</option>
                    {allColumnNames.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Real-time Target Validation & Diagnostics */}
                {(() => {
                  const targetProf = columns.find((c) => c.name === targetColumn);
                  if (!targetProf || !targetColumn) return null;

                  const isTargetNumeric = targetProf.inferred_type === 'numeric';
                  const isHighCard = targetProf.unique_count > 15;
                  const valSupportPerClass = targetProf.unique_count > 0
                    ? ((dataset?.row_count || 0) * 0.2 / targetProf.unique_count).toFixed(1)
                    : '0';

                  return (
                    <div className="space-y-2 max-w-3xl">
                      {/* Classification Warning on Numeric / High-Cardinality Target */}
                      {taskType === 'classification' && (isTargetNumeric || isHighCard) && (
                        <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 rounded-xl text-xs text-amber-900 dark:text-amber-200">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start space-x-2">
                              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                              <div>
                                <span className="font-bold text-amber-950 dark:text-amber-100">
                                  High-Cardinality Classification Target Warning
                                </span>
                                <p className="mt-0.5 opacity-90 leading-relaxed">
                                  Selected target <code className="font-mono font-bold bg-amber-100 dark:bg-amber-900/60 px-1 py-0.5 rounded">{targetColumn}</code> is {isTargetNumeric ? 'numeric' : 'categorical'} with {targetProf.unique_count} distinct values.
                                  Running multi-class classification on high-cardinality targets creates severe data sparsity (~{valSupportPerClass} validation examples per class) and degraded Macro-F1 scores.
                                </p>
                                <p className="mt-1.5 font-semibold text-amber-800 dark:text-amber-300">
                                  Recommendation: We recommend Regression for continuous numeric quantities unless discrete multi-class classification is explicitly intended.
                                </p>
                              </div>
                            </div>
                            {isTargetNumeric && (
                              <button
                                type="button"
                                onClick={() => handleTaskTypeChange('regression')}
                                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-bold text-[11px] whitespace-nowrap shadow-xs flex-shrink-0"
                              >
                                Switch to Regression
                              </button>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Classification Target Diagnostics & Support Card */}
                      {taskType === 'classification' && (
                        <div className="p-3.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 rounded-xl text-xs space-y-2.5">
                          <div className="flex items-center justify-between text-slate-700 dark:text-slate-300 font-bold">
                            <span className="flex items-center space-x-1.5">
                              <Activity className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                              <span>Classification Target Diagnostics</span>
                            </span>
                            <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                              {targetProf.unique_count} distinct classes
                            </span>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                            <div className="p-2 bg-white dark:bg-slate-900 rounded-lg border border-slate-100 dark:border-slate-800">
                              <span className="text-slate-400 block text-[10px]">Total Classes</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200 font-mono text-xs">
                                {targetProf.unique_count}
                              </span>
                            </div>
                            <div className="p-2 bg-white dark:bg-slate-900 rounded-lg border border-slate-100 dark:border-slate-800">
                              <span className="text-slate-400 block text-[10px]">Est. Validation Support</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200 font-mono text-xs">
                                ~{valSupportPerClass} / class
                              </span>
                            </div>
                            <div className="p-2 bg-white dark:bg-slate-900 rounded-lg border border-slate-100 dark:border-slate-800">
                              <span className="text-slate-400 block text-[10px]">Majority Class Share</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200 font-mono text-xs">
                                {targetProf.top_categories?.[0] ? `${targetProf.top_categories[0].percentage}%` : 'N/A'}
                              </span>
                            </div>
                            <div className="p-2 bg-white dark:bg-slate-900 rounded-lg border border-slate-100 dark:border-slate-800">
                              <span className="text-slate-400 block text-[10px]">Distribution Balance</span>
                              <span className={`font-bold font-mono text-xs ${
                                (targetProf.top_categories?.[0]?.percentage || 0) > 40
                                  ? 'text-amber-600 dark:text-amber-400'
                                  : 'text-emerald-600 dark:text-emerald-400'
                              }`}>
                                {(targetProf.top_categories?.[0]?.percentage || 0) > 40 ? 'Imbalanced' : 'Balanced'}
                              </span>
                            </div>
                          </div>

                          {targetProf.top_categories && targetProf.top_categories.length > 0 && (
                            <div className="pt-1">
                              <span className="text-[10px] font-semibold text-slate-400 block mb-1 uppercase tracking-wider">
                                Class Distribution Sample:
                              </span>
                              <div className="flex flex-wrap gap-1.5">
                                {targetProf.top_categories.slice(0, 5).map((cat: any) => (
                                  <span
                                    key={cat.value}
                                    className="px-2 py-0.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded text-[10px] text-slate-700 dark:text-slate-300 font-mono"
                                  >
                                    <strong>{cat.value}</strong>: {cat.count} ({cat.percentage}%)
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Incompatible Non-numeric Target Warning for Regression / Forecasting */}
                      {(taskType === 'regression' || taskType === 'forecasting') && targetProf.inferred_type === 'categorical' && (
                        <div className="p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-300 dark:border-red-900 rounded-xl text-xs text-red-900 dark:text-red-200 flex items-start space-x-2">
                          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                          <div>
                            <span className="font-bold">Incompatible Target Column Type</span>
                            <p className="mt-0.5 opacity-90 leading-relaxed">
                              Target <code className="font-mono font-bold bg-red-100 dark:bg-red-900/60 px-1 py-0.5 rounded">{targetColumn}</code> is inferred as categorical text. Regression and demand forecasting require a continuous numeric dependent variable.
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Date Column Selector (Forecasting) */}
            {taskType === 'forecasting' && (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    3. Date / Time Column (Chronological Axis)
                  </label>
                  <select
                    value={dateColumn}
                    onChange={(e) => handleDateColumnChange(e.target.value)}
                    required
                    className="w-full sm:w-80 px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 font-mono focus:ring-2 focus:ring-brand-500 outline-none"
                  >
                    <option value="">-- Choose Date Column --</option>
                    {allColumnNames.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Expiration Date Semantic Advisory */}
                {dateColumn && (() => {
                  const lowerDate = dateColumn.toLowerCase();
                  const isExpir = lowerDate.includes('expir') || lowerDate.includes('shelf_life') || lowerDate.includes('best_before') || lowerDate.includes('use_by');
                  if (!isExpir) return null;

                  const genuineCandidates = allColumnNames.filter((c) => {
                    const lc = c.toLowerCase();
                    return (
                      c !== dateColumn &&
                      c !== targetColumn &&
                      (lc.includes('date') || lc.includes('time') || lc.includes('order') || lc.includes('received') || lc.includes('sale'))
                    );
                  });

                  return (
                    <div className="p-4 bg-amber-50/80 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 rounded-xl text-xs text-amber-900 dark:text-amber-200 space-y-2 max-w-3xl">
                      <div className="flex items-start space-x-2">
                        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                        <div>
                          <span className="font-bold text-amber-950 dark:text-amber-100">
                            Advisory: Product Shelf-Life Expiration Date Selected
                          </span>
                          <p className="mt-0.5 opacity-90 leading-relaxed">
                            <code className="font-mono font-bold bg-amber-100 dark:bg-amber-900/60 px-1 py-0.5 rounded">{dateColumn}</code> represents product shelf life rather than the chronological timeline of demand or inventory movements.
                            Time-series forecasting models produce far more accurate predictions when indexed on actual ordering or receiving timestamps.
                          </p>
                          {genuineCandidates.length > 0 && (
                            <div className="mt-2.5 flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-amber-800 dark:text-amber-300">
                                Recommended observation timestamp{genuineCandidates.length > 1 ? 's' : ''}:
                              </span>
                              {genuineCandidates.map((alt) => (
                                <button
                                  key={alt}
                                  type="button"
                                  onClick={() => handleDateColumnChange(alt)}
                                  className="px-2.5 py-1 bg-amber-200/80 hover:bg-amber-300 dark:bg-amber-900/70 dark:hover:bg-amber-800 text-amber-950 dark:text-amber-100 rounded-md font-mono text-[11px] font-semibold transition-colors flex items-center space-x-1"
                                >
                                  <span>Use {alt}</span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Feature Columns Selection */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
                  {taskType === 'forecasting' ? '4' : taskType === 'anomaly' ? '2' : '3'}. Feature Columns ({selectedFeatures.length} selected)
                </label>
                <div className="space-x-2 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      clearMessages();
                      setSelectedFeatures(
                        allColumnNames.filter(
                          (c) => c !== targetColumn && (taskType !== 'forecasting' || c !== dateColumn)
                        )
                      );
                    }}
                    className="text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Select All
                  </button>
                  <span className="text-slate-300 dark:text-slate-700">|</span>
                  <button
                    type="button"
                    onClick={() => {
                      clearMessages();
                      setSelectedFeatures([]);
                    }}
                    className="text-slate-500 dark:text-slate-400 hover:underline"
                  >
                    Clear All
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 border border-slate-200 dark:border-slate-800 rounded-xl p-3 bg-slate-50/50 dark:bg-slate-950/40 max-h-64 overflow-y-auto">
                {allColumnNames.map((col) => {
                  const isTarget = taskType !== 'anomaly' && col === targetColumn;
                  const isDate = taskType === 'forecasting' && col === dateColumn;
                  const isChecked = selectedFeatures.includes(col);

                  if (isTarget) {
                    return (
                      <div
                        key={col}
                        title={`'${col}' is the target variable (prediction output) and cannot be included as an input feature.`}
                        className="flex items-center justify-between p-2 rounded-lg text-xs bg-amber-50/60 dark:bg-amber-950/30 border border-amber-200/80 dark:border-amber-900/40 opacity-75 cursor-not-allowed select-none"
                      >
                        <div className="flex items-center space-x-2 min-w-0">
                          <input
                            type="checkbox"
                            disabled
                            checked={false}
                            className="rounded text-amber-500 opacity-50 cursor-not-allowed"
                          />
                          <span className="truncate font-mono text-amber-900 dark:text-amber-200">{col}</span>
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-200/70 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200 flex-shrink-0 ml-1">
                          Target
                        </span>
                      </div>
                    );
                  }

                  if (isDate) {
                    return (
                      <div
                        key={col}
                        title={`'${col}' is configured as the chronological date axis for time-series engineering and cannot be a static feature.`}
                        className="flex items-center justify-between p-2 rounded-lg text-xs bg-purple-50/60 dark:bg-purple-950/30 border border-purple-200/80 dark:border-purple-900/40 opacity-75 cursor-not-allowed select-none"
                      >
                        <div className="flex items-center space-x-2 min-w-0">
                          <input
                            type="checkbox"
                            disabled
                            checked={false}
                            className="rounded text-purple-500 opacity-50 cursor-not-allowed"
                          />
                          <span className="truncate font-mono text-purple-900 dark:text-purple-200">{col}</span>
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-purple-200/70 dark:bg-purple-900/60 text-purple-800 dark:text-purple-200 flex-shrink-0 ml-1">
                          Date Axis
                        </span>
                      </div>
                    );
                  }

                  return (
                    <label
                      key={col}
                      className={`flex items-center space-x-2 p-2 rounded-lg text-xs cursor-pointer select-none transition-colors ${
                        isChecked
                          ? 'bg-brand-50 dark:bg-blue-950/60 font-semibold text-brand-900 dark:text-blue-300 border border-brand-200 dark:border-blue-900/60'
                          : 'hover:bg-white dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 border border-transparent'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleFeature(col)}
                        className="rounded text-brand-600 focus:ring-brand-500"
                      />
                      <span className="truncate font-mono">{col}</span>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Grouping / Entity Columns */}
            <div>
              <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                Optional Grouping / Entity Columns (e.g. SKU, Warehouse, Store ID)
              </label>
              <div className="flex flex-wrap gap-2">
                {allColumnNames
                  .filter((c) => c !== targetColumn && (taskType !== 'forecasting' || c !== dateColumn))
                  .map((col) => (
                    <button
                      key={col}
                      type="button"
                      onClick={() => toggleEntity(col)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors border ${
                        selectedEntities.includes(col)
                          ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-800 dark:text-purple-300 border-purple-300 dark:border-purple-800 font-bold'
                          : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'
                      }`}
                    >
                      {col}
                    </button>
                  ))}
              </div>
            </div>

            {/* Action Buttons: Save Config & Train Models */}
            <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center justify-end gap-3">
              <button
                type="submit"
                disabled={configSaving}
                className="inline-flex items-center space-x-2 px-5 py-2.5 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-lg text-sm font-semibold transition-all shadow-sm disabled:opacity-50"
              >
                <Save className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                <span>{configSaving ? 'Saving...' : 'Save Configuration'}</span>
              </button>

              <button
                type="button"
                onClick={handleStartTraining}
                disabled={
                  trainingStarting ||
                  activeRun?.status === 'RUNNING' ||
                  activeRun?.status === 'QUEUED' ||
                  selectedFeatures.length === 0
                }
                className="inline-flex items-center space-x-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition-all shadow-sm disabled:opacity-50 cursor-pointer"
              >
                {trainingStarting || activeRun?.status === 'RUNNING' || activeRun?.status === 'QUEUED' ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Training in Progress...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    <span>Train Candidate Models</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Historical Training Runs Table */}
          {trainingRuns.length > 0 && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-6 shadow-sm mt-6 transition-colors">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">Historical Training Runs</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Review previously trained candidate models and their validation performance.
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto custom-scrollbar">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-300 font-semibold uppercase">
                      <th className="py-2.5 px-3">Run ID</th>
                      <th className="py-2.5 px-3">Task</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Candidates</th>
                      <th className="py-2.5 px-3">Duration</th>
                      <th className="py-2.5 px-3">Created</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {trainingRuns.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-3 font-mono text-[11px] text-slate-600 dark:text-slate-400">{r.id.slice(0, 8)}...</td>
                        <td className="py-3 px-3 font-medium uppercase text-slate-800 dark:text-slate-200">{r.task_type}</td>
                        <td className="py-3 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                              r.status === 'COMPLETED'
                                ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300'
                                : r.status === 'RUNNING' || r.status === 'QUEUED'
                                ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 animate-pulse'
                                : 'bg-red-100 dark:bg-red-950/60 text-red-800 dark:text-red-300'
                            }`}
                          >
                            {r.status}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-slate-600 dark:text-slate-400">{r.candidate_count} models</td>
                        <td className="py-3 px-3 text-slate-600 dark:text-slate-400">{r.duration_seconds}s</td>
                        <td className="py-3 px-3 text-slate-500 dark:text-slate-400">{new Date(r.created_at).toLocaleString()}</td>
                        <td className="py-3 px-3 text-right">
                          {r.status === 'COMPLETED' ? (
                            <button
                              type="button"
                              onClick={() => navigate(`/models?run_id=${r.id}&dataset_id=${id}`)}
                              className="inline-flex items-center space-x-1 text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 font-semibold"
                            >
                              <span>View in Lab</span>
                              <ExternalLink className="w-3 h-3" />
                            </button>
                          ) : (
                            <span className="text-slate-400 italic">--</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

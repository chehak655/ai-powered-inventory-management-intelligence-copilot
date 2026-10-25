import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { datasetApi } from '../services/api';
import { Dataset } from '../types';
import {
  Upload,
  FileSpreadsheet,
  FileText,
  Trash2,
  Sliders,
  Download,
  Search,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Plus,
  X,
} from 'lucide-react';

export const DatasetsPage: React.FC = () => {
  const navigate = useNavigate();
  const { activeCompany } = useAuth();
  const isOwner = activeCompany?.role === 'OWNER';

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDatasets = async () => {
    if (!activeCompany) return;
    setLoading(true);
    try {
      const data = await datasetApi.list(page, 10, search);
      setDatasets(data.items);
      setTotal(data.total);
    } catch (err: any) {
      console.error('Failed to load datasets:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDatasets();
  }, [page, search, activeCompany?.id]);

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      handleFileSelected(file);
    }
  };

  const handleFileSelected = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'csv' && ext !== 'xlsx') {
      setUploadError('Only CSV (.csv) and Excel (.xlsx) files are supported.');
      return;
    }
    setSelectedFile(file);
    setDatasetName(file.name.replace(/\.[^/.]+$/, ''));
    setUploadError(null);
  };

  const handleCloseModal = () => {
    if (uploading) return;
    setShowUploadModal(false);
    setSelectedFile(null);
    setDatasetName('');
    setUploadError(null);
    setUploadProgress(0);
    setIsDragOver(false);
  };

  // Lock body scroll and prevent layout shift while modal is open
  useEffect(() => {
    if (!showUploadModal) return;
    const originalOverflow = document.body.style.overflow;
    const originalPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

    document.body.style.overflow = 'hidden';
    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${scrollbarWidth}px`;
    }

    return () => {
      document.body.style.overflow = originalOverflow;
      document.body.style.paddingRight = originalPaddingRight;
    };
  }, [showUploadModal]);

  // Close on Escape key press
  useEffect(() => {
    if (!showUploadModal) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !uploading) {
        handleCloseModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showUploadModal, uploading]);

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setUploadProgress(0);
    setUploadError(null);

    try {
      await datasetApi.upload(selectedFile, datasetName, (progress) => {
        setUploadProgress(progress);
      });
      handleCloseModal();
      fetchDatasets();
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Upload failed.';
      setUploadError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Are you sure you want to delete dataset '${name}'? This cannot be undone.`)) {
      return;
    }

    try {
      await datasetApi.delete(id);
      fetchDatasets();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete dataset.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">Datasets & Data Quality</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Upload CSV/Excel inventories, inspect profiling diagnostics, and configure prediction columns.
          </p>
        </div>

        <button
          onClick={() => setShowUploadModal(true)}
          className="inline-flex items-center space-x-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-semibold transition-all shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span>Upload Dataset</span>
        </button>
      </div>

      {/* Search and Filters */}
      <div className="flex items-center space-x-3 bg-white dark:bg-slate-900 p-3 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm transition-colors">
        <Search className="w-4 h-4 text-slate-400 ml-2" />
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search datasets by name..."
          className="w-full text-sm outline-none text-slate-700 dark:text-slate-200 bg-transparent placeholder-slate-400 dark:placeholder-slate-500"
        />
        {search && (
          <button onClick={() => setSearch('')} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded text-slate-400">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Datasets Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden transition-colors">
        {loading ? (
          <div className="p-12 text-center text-slate-500 dark:text-slate-400 flex flex-col items-center justify-center space-y-2">
            <RefreshCw className="w-6 h-6 animate-spin text-brand-600" />
            <span className="text-sm">Loading workspace datasets...</span>
          </div>
        ) : datasets.length === 0 ? (
          <div className="p-16 text-center">
            <FileSpreadsheet className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-slate-800 dark:text-slate-200">No datasets found</h3>
            <p className="text-slate-500 dark:text-slate-400 text-sm max-w-sm mx-auto mt-1 mb-5">
              Upload your company sales records, inventory stock lists, or store demand logs to get started.
            </p>
            <button
              onClick={() => setShowUploadModal(true)}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700"
            >
              <Plus className="w-4 h-4" />
              <span>Upload Your First Dataset</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-left text-sm text-slate-700 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-500 dark:text-slate-300 uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 px-4">Dataset Name</th>
                  <th className="py-3.5 px-4">Format</th>
                  <th className="py-3.5 px-4">Dimensions</th>
                  <th className="py-3.5 px-4">Quality Score</th>
                  <th className="py-3.5 px-4">File Size</th>
                  <th className="py-3.5 px-4">Uploaded</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {datasets.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/60 transition-colors">
                    <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                      {d.file_format === 'csv' ? (
                        <FileText className="w-4 h-4 text-blue-500 flex-shrink-0" />
                      ) : (
                        <FileSpreadsheet className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                      )}
                      <span className="truncate max-w-xs">{d.name}</span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                        {d.file_format}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-400">
                      {d.row_count.toLocaleString()} rows × {d.column_count} cols
                    </td>
                    <td className="py-3.5 px-4">
                      {d.validation_summary?.health_score !== undefined ? (
                        <span
                          className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
                            d.validation_summary.health_score >= 80
                              ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60'
                              : d.validation_summary.health_score >= 60
                              ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60'
                              : 'bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800/60'
                          }`}
                        >
                          {d.validation_summary.health_score >= 80 ? (
                            <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                          ) : (
                            <AlertTriangle className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                          )}
                          <span>{d.validation_summary.health_score}%</span>
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">N/A</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400 text-xs">
                      {(d.file_size_bytes / 1024).toFixed(1)} KB
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400 text-xs">
                      {new Date(d.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3.5 px-4 text-right space-x-2 whitespace-nowrap">
                      <button
                        onClick={() => navigate(`/datasets/${d.id}`)}
                        className="inline-flex items-center space-x-1 px-2.5 py-1.5 rounded-lg bg-brand-50 dark:bg-blue-900/50 text-brand-700 dark:text-blue-300 hover:bg-brand-100 dark:hover:bg-blue-800/60 border border-transparent dark:border-blue-800/60 focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium text-xs transition-colors"
                        title="Inspect profiling & configure columns"
                      >
                        <Sliders className="w-3.5 h-3.5" />
                        <span>Inspect & Configure</span>
                      </button>

                      <a
                        href={datasetApi.downloadUrl(d.id)}
                        download={d.original_filename}
                        className="inline-flex items-center p-1.5 rounded-lg text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 dark:focus:ring-slate-600 transition-colors"
                        title="Download file"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </a>

                      {isOwner && (
                        <button
                          onClick={() => handleDelete(d.id, d.name)}
                          className="inline-flex items-center p-1.5 rounded-lg text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/50 focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
                          title="Delete dataset"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination Controls */}
            {total > 10 && (
              <div className="p-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>Showing {datasets.length} of {total} datasets</span>
                <div className="flex space-x-1">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    className="px-2.5 py-1 border border-slate-200 dark:border-slate-700 rounded hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="px-3 py-1 font-semibold text-slate-700 dark:text-slate-300">Page {page}</span>
                  <button
                    disabled={page * 10 >= total}
                    onClick={() => setPage(page + 1)}
                    className="px-2.5 py-1 border border-slate-200 dark:border-slate-700 rounded hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Upload Modal (Portaled to document.body to break out of .space-y-6 and parent scroll/layout contexts) */}
      {showUploadModal &&
        createPortal(
          <div
            className="fixed inset-0 m-0 p-4 sm:p-6 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm transition-opacity duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget) {
                handleCloseModal();
              }
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-modal-title"
            aria-describedby="upload-modal-description"
          >
            <div
              className="relative w-full max-w-lg my-auto rounded-2xl bg-white dark:bg-slate-900 p-6 shadow-2xl border border-slate-200 dark:border-slate-800 transition-colors max-h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-3rem)] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                onClick={handleCloseModal}
                disabled={uploading}
                className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50"
                aria-label="Close upload dialog"
              >
                <X className="w-5 h-5" />
              </button>

              <h2 id="upload-modal-title" className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-1">
                Upload New Dataset
              </h2>
              <p id="upload-modal-description" className="text-xs text-slate-500 dark:text-slate-400 mb-5">
                Supports CSV (.csv) and Excel (.xlsx) files up to 50MB.
              </p>

              <form onSubmit={handleUploadSubmit} className="space-y-4">
                {uploadError && (
                  <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-lg text-xs text-red-700 dark:text-red-300 flex items-start space-x-2">
                    <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                    <span>{uploadError}</span>
                  </div>
                )}

                {/* Drag and drop zone */}
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragOver(true);
                  }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                    isDragOver
                      ? 'border-brand-500 bg-brand-50/50 dark:bg-blue-950/40'
                      : selectedFile
                      ? 'border-emerald-400 dark:border-emerald-600 bg-emerald-50/30 dark:bg-emerald-950/20'
                      : 'border-slate-300 dark:border-slate-700 hover:border-brand-400 dark:hover:border-brand-500 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        handleFileSelected(e.target.files[0]);
                      }
                    }}
                  />

                  <Upload className="w-8 h-8 text-brand-600 dark:text-brand-400 mx-auto mb-2" />
                  {selectedFile ? (
                    <div>
                      <div className="font-semibold text-sm text-slate-800 dark:text-slate-200">{selectedFile.name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        {(selectedFile.size / 1024).toFixed(1)} KB • Click or drag to replace
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div className="font-medium text-sm text-slate-700 dark:text-slate-300">Click or drag file here to upload</div>
                      <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">CSV or XLSX formats up to 50MB</div>
                    </div>
                  )}
                </div>

                {/* Dataset Display Name */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    Dataset Display Name
                  </label>
                  <input
                    type="text"
                    value={datasetName}
                    onChange={(e) => setDatasetName(e.target.value)}
                    placeholder="e.g. 2026 Inventory Demand Logs"
                    required
                    disabled={uploading}
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  />
                </div>

                {/* Progress bar */}
                {uploading && (
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-slate-600 dark:text-slate-400">
                      <span>Uploading and profiling dataset...</span>
                      <span>{uploadProgress}%</span>
                    </div>
                    <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-600 transition-all duration-300"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                )}

                <div className="flex justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={handleCloseModal}
                    className="px-4 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!selectedFile || uploading}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition-colors shadow-sm disabled:opacity-50"
                  >
                    {uploading ? 'Processing...' : 'Upload & Profile'}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
};

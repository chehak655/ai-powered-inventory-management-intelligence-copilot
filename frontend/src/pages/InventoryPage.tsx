import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { datasetApi, inventoryApi } from '../services/api';
import { Dataset, InventoryKPIsResponse, InventoryItem } from '../types';
import {
  Boxes,
  AlertTriangle,
  CheckCircle2,
  TrendingDown,
  DollarSign,
  PackageCheck,
  Bot,
  Filter,
  ArrowRight,
  ShieldAlert,
  Clock,
  Sparkles,
  RefreshCw,
} from 'lucide-react';

export const InventoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [serviceLevel, setServiceLevel] = useState<number>(0.95);
  const [kpis, setKpis] = useState<InventoryKPIsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  useEffect(() => {
    datasetApi.list(1, 50).then((res) => {
      setDatasets(res.items);
      if (res.items.length > 0) {
        setSelectedDatasetId(res.items[0].id);
      }
    });
  }, []);

  useEffect(() => {
    if (!selectedDatasetId) return;
    setLoading(true);
    inventoryApi
      .getKpis(selectedDatasetId, serviceLevel)
      .then((data) => {
        setKpis(data);
      })
      .catch((err) => {
        console.error('Failed to load inventory KPIs:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [selectedDatasetId, serviceLevel]);

  const filteredItems = (kpis?.items || []).filter((item) => {
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'CRITICAL_REORDER') return item.status === 'CRITICAL' || item.status === 'REORDER_NOW';
    return item.status === statusFilter;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-200/80 dark:border-slate-800 gap-4">
        <div>
          <div className="flex items-center space-x-2 text-brand-600 dark:text-brand-400 text-xs font-bold uppercase tracking-wider">
            <Boxes className="w-4 h-4" />
            <span>Phase G • Inventory Optimization & Supply Chain Intelligence</span>
          </div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-slate-100 tracking-tight mt-1">Inventory Analytics</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Dynamic Safety Stock, Reorder Points, and stockout vulnerability tracking powered by machine learning demand signals.
          </p>
        </div>

        {/* Dataset & Service Level Controls */}
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
              Service Level Z-Target
            </label>
            <select
              value={serviceLevel}
              onChange={(e) => setServiceLevel(Number(e.target.value))}
              className="bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-xs font-semibold px-3 py-2 text-slate-800 dark:text-slate-200 focus:ring-brand-500 focus:border-brand-500"
            >
              <option value={0.9}>90% (Z=1.28) • Economy</option>
              <option value={0.95}>95% (Z=1.65) • Standard Balanced</option>
              <option value={0.99}>99% (Z=2.33) • High Criticality</option>
            </select>
          </div>

          <button
            onClick={() => navigate('/copilot')}
            className="inline-flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-all shadow-sm self-end"
          >
            <Bot className="w-3.5 h-3.5" />
            <span>Consult Copilot</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p-16 text-center text-slate-400 text-sm">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-brand-600" />
          Computing safety stock and reorder point models...
        </div>
      ) : !kpis ? (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-12 text-center max-w-md mx-auto shadow-sm">
          <Boxes className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800 dark:text-slate-200">No Inventory Data Found</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Upload a sales or inventory dataset to view intelligence KPIs.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* KPI Summary Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Critical Stockouts */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-red-200 dark:border-red-900/60 p-5 shadow-2xs relative overflow-hidden transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-red-600 dark:text-red-400">
                  Critical Stockout Risk
                </span>
                <ShieldAlert className="w-4 h-4 text-red-500" />
              </div>
              <div className="text-3xl font-black text-red-700 dark:text-red-400">{kpis.summary.critical_stockouts}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">SKUs with inventory &le; 50% ROP</div>
            </div>

            {/* Reorder Needed */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-amber-200 dark:border-amber-900/60 p-5 shadow-2xs relative overflow-hidden transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                  Reorder Needed
                </span>
                <Clock className="w-4 h-4 text-amber-500" />
              </div>
              <div className="text-3xl font-black text-amber-700 dark:text-amber-400">{kpis.summary.reorder_needed}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">SKUs at or below reorder threshold</div>
            </div>

            {/* Trapped Capital at Risk */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-purple-200 dark:border-purple-900/60 p-5 shadow-2xs relative overflow-hidden transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400">
                  Overstock Capital at Risk
                </span>
                <DollarSign className="w-4 h-4 text-purple-500" />
              </div>
              <div className="text-3xl font-black text-purple-900 dark:text-purple-300">
                ${kpis.summary.overstock_capital_at_risk.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">{kpis.summary.overstocked} products with excess inventory</div>
            </div>

            {/* Total Inventory Value */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-2xs relative overflow-hidden transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Total Inventory Valuation
                </span>
                <PackageCheck className="w-4 h-4 text-slate-400" />
              </div>
              <div className="text-3xl font-black text-slate-900 dark:text-slate-100">
                ${kpis.summary.total_inventory_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">{kpis.summary.total_skus} total catalog SKUs tracked</div>
            </div>
          </div>

          {/* Catalog Table */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden shadow-sm transition-colors">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">SKU Inventory Vulnerability Table</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Formula: Safety Stock SS = Z × σ_d × √L • Reorder Point ROP = (d̄ × L) + SS
                </p>
              </div>

              {/* Status Filter Buttons */}
              <div className="flex flex-wrap items-center gap-1.5">
                {[
                  { id: 'ALL', label: 'All Items' },
                  { id: 'CRITICAL_REORDER', label: 'Needs Order (Critical)' },
                  { id: 'HEALTHY', label: 'Healthy' },
                  { id: 'OVERSTOCK', label: 'Overstocked' },
                ].map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setStatusFilter(f.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                      statusFilter === f.id
                        ? 'bg-slate-900 dark:bg-brand-600 text-white'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-300 font-semibold uppercase">
                    <th className="py-3 px-4">SKU / Product</th>
                    <th className="py-3 px-4 font-mono">Current Stock</th>
                    <th className="py-3 px-4 font-mono">Daily Demand (d̄)</th>
                    <th className="py-3 px-4 font-mono">Lead Time</th>
                    <th className="py-3 px-4 font-mono">Safety Stock</th>
                    <th className="py-3 px-4 font-mono">Reorder Point (ROP)</th>
                    <th className="py-3 px-4 font-mono">Days of Supply</th>
                    <th className="py-3 px-4">Risk Status</th>
                    <th className="py-3 px-4 font-mono text-right">Recommend Order</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {filteredItems.map((item) => (
                    <tr key={item.sku} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors">
                      <td className="py-3 px-4 font-mono font-bold text-slate-900 dark:text-slate-100">{item.sku}</td>
                      <td className="py-3 px-4 font-mono text-slate-700 dark:text-slate-300">{item.current_stock}</td>
                      <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">{item.daily_demand}/day</td>
                      <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">{item.lead_time_days}d</td>
                      <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400 font-semibold">{item.safety_stock}</td>
                      <td className="py-3 px-4 font-mono text-slate-900 dark:text-slate-100 font-bold">{item.reorder_point}</td>
                      <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">{item.days_of_supply} days</td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                            item.status === 'CRITICAL'
                              ? 'bg-red-100 dark:bg-red-950/60 text-red-800 dark:text-red-300'
                              : item.status === 'REORDER_NOW'
                              ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300'
                              : item.status === 'OVERSTOCK'
                              ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-800 dark:text-purple-300'
                              : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300'
                          }`}
                        >
                          {item.status.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-right font-bold">
                        {item.recommended_reorder_qty > 0 ? (
                          <span className="text-red-600 dark:text-red-400">+{item.recommended_reorder_qty} units</span>
                        ) : (
                          <span className="text-slate-400 dark:text-slate-500">0</span>
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
    </div>
  );
};

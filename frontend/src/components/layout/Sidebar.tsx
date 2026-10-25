import React from 'react';
import { NavLink } from 'react-router-dom';
import { Database, Cpu, Layers, Sparkles, Boxes, Bot, Users } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const Sidebar: React.FC = () => {
  const { activeCompany, pendingRequestsCount } = useAuth();
  const isOwner = activeCompany?.role === 'OWNER';

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
      isActive
        ? 'bg-brand-50 dark:bg-blue-950/60 text-brand-700 dark:text-blue-300 shadow-sm border border-brand-100 dark:border-blue-900/50'
        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100'
    }`;

  return (
    <aside className="w-64 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col justify-between p-4 min-h-[calc(100vh-4rem)] transition-colors duration-150">
      <div className="space-y-1">
        <div className="px-3 py-2 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
          Data & ML Pipeline
        </div>

        <NavLink to="/datasets" className={linkClass}>
          <Database className="h-4 w-4" />
          <span>Datasets & Quality</span>
        </NavLink>

        <NavLink to="/models" className={linkClass}>
          <Cpu className="h-4 w-4" />
          <span>Model Lab</span>
        </NavLink>

        <NavLink to="/registry" className={linkClass}>
          <Layers className="h-4 w-4" />
          <span>Model Registry</span>
        </NavLink>

        <NavLink to="/predictions" className={linkClass}>
          <Sparkles className="h-4 w-4" />
          <span>Predictions</span>
        </NavLink>

        <div className="pt-4 px-3 py-2 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
          Business Intelligence
        </div>

        <NavLink to="/inventory" className={linkClass}>
          <Boxes className="h-4 w-4" />
          <span>Inventory Analytics</span>
        </NavLink>

        <NavLink to="/copilot" className={linkClass}>
          <Bot className="h-4 w-4" />
          <span>AI Copilot</span>
        </NavLink>

        {isOwner && (
          <>
            <div className="pt-4 px-3 py-2 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
              Workspace Administration
            </div>
            <NavLink to="/team" className={linkClass}>
              <Users className="h-4 w-4 shrink-0" />
              <span className="truncate">Team Management</span>
              {pendingRequestsCount > 0 && (
                <span
                  className="px-2 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-300 border border-amber-300/60 dark:border-amber-700/50 rounded-full font-bold shrink-0 ml-1.5"
                  title={`${pendingRequestsCount} pending join request${pendingRequestsCount === 1 ? '' : 's'}`}
                  aria-label={`${pendingRequestsCount} pending join requests`}
                >
                  {pendingRequestsCount > 99 ? '99+' : pendingRequestsCount}
                </span>
              )}
            </NavLink>
          </>
        )}
      </div>

      <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400 space-y-1">
        <div className="font-semibold text-slate-700 dark:text-slate-200">AI Powered Inventory</div>
        <div>Intelligence Copilot & ML Engine</div>
        <div className="text-[10px] text-slate-400 dark:text-slate-500 pt-1">Production Verified • v1.0</div>
      </div>
    </aside>
  );
};

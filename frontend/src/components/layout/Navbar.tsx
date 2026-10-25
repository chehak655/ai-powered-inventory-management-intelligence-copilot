import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { Building2, ChevronDown, LogOut, Sun, Moon } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { user, companies, activeCompany, setActiveCompany, logout } = useAuth();
  const { theme, isDark, toggleTheme } = useTheme();

  return (
    <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6 flex items-center justify-between sticky top-0 z-30 shadow-sm transition-colors duration-150">
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2" title="AI Powered Inventory Management and Intelligence Copilot">
          <div className="h-9 w-9 rounded-lg bg-brand-600 flex items-center justify-center text-white font-bold text-sm shadow-sm tracking-wider">
            AI
          </div>
          <span className="font-bold text-lg text-slate-900 dark:text-slate-100 tracking-tight">
            AI Inventory <span className="text-brand-600 dark:text-brand-400 font-extrabold">Copilot</span>
          </span>
        </div>

        {/* Workspace Selector */}
        {companies.length > 0 && (
          <div className="relative group ml-6">
            <div className="flex items-center space-x-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors px-3 py-1.5 rounded-lg cursor-pointer text-sm font-medium text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700">
              <Building2 className="h-4 w-4 text-brand-600 dark:text-brand-400" />
              <span>{activeCompany?.name || 'Select Workspace'}</span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-brand-100 dark:bg-brand-900/60 text-brand-700 dark:text-brand-300 font-semibold uppercase">
                {activeCompany?.role || 'Member'}
              </span>
              <ChevronDown className="h-4 w-4 text-slate-500 dark:text-slate-400" />
            </div>

            <div className="absolute left-0 mt-1 w-64 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg shadow-lg hidden group-hover:block py-1 z-50">
              <div className="px-3 py-1.5 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                Your Workspaces
              </div>
              {companies.map((comp) => (
                <button
                  key={comp.id}
                  onClick={() => setActiveCompany(comp)}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors ${
                    activeCompany?.id === comp.id
                      ? 'bg-brand-50 dark:bg-brand-950/60 font-semibold text-brand-700 dark:text-brand-300'
                      : 'text-slate-700 dark:text-slate-300'
                  }`}
                >
                  <span className="truncate">{comp.name}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium uppercase">
                    {comp.role}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center space-x-3 sm:space-x-4">
        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          className="flex items-center space-x-1.5 p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-amber-400 hover:bg-slate-100 dark:hover:bg-slate-700/80 transition-all focus:outline-none focus:ring-2 focus:ring-brand-500 shadow-sm"
        >
          {isDark ? (
            <Sun className="h-4 w-4 text-amber-400 transition-transform hover:rotate-45" />
          ) : (
            <Moon className="h-4 w-4 text-slate-600 transition-transform hover:-rotate-12" />
          )}
          <span className="hidden md:inline text-xs font-medium text-slate-600 dark:text-slate-300">
            {isDark ? 'Light' : 'Dark'}
          </span>
        </button>

        {user && (
          <div className="flex items-center space-x-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{user.full_name}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">{user.email}</div>
            </div>
            <button
              onClick={logout}
              className="flex items-center space-x-1.5 text-sm text-slate-600 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 p-2 rounded-lg transition-colors border border-transparent hover:border-red-100 dark:hover:border-red-900/50"
              title="Sign Out"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

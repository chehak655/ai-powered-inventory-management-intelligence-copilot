import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { authApi } from '../services/api';
import { Building2, Lock, Mail, User as UserIcon, AlertCircle, Sun, Moon, CheckCircle2, Users, ArrowRight } from 'lucide-react';

type AuthMode = 'login' | 'register_owner' | 'join_worker';

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const { isDark, toggleTheme } = useTheme();

  const [mode, setMode] = useState<AuthMode>('login');

  // Form states
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [workspaceSlug, setWorkspaceSlug] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Success state for worker join request
  const [joinSuccess, setJoinSuccess] = useState<{
    companyName: string;
    email: string;
  } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === 'register_owner') {
        if (!email || !password || !fullName || !companyName) {
          setError('Please fill in all registration fields.');
          setLoading(false);
          return;
        }
        if (password.length < 6) {
          setError('Password must be at least 6 characters.');
          setLoading(false);
          return;
        }
        await register(email, password, fullName, companyName);
        navigate('/datasets');
      } else if (mode === 'join_worker') {
        if (!email || !password || !fullName || !workspaceSlug) {
          setError('Please fill in all required fields.');
          setLoading(false);
          return;
        }
        if (password.length < 6) {
          setError('Password must be at least 6 characters.');
          setLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError('Passwords do not match.');
          setLoading(false);
          return;
        }

        const res = await authApi.submitJoinRequest({
          full_name: fullName.trim(),
          email: email.trim(),
          password,
          workspace_slug: workspaceSlug.trim(),
        });

        setJoinSuccess({
          companyName: res.company_name,
          email: res.email,
        });
      } else {
        // Sign In
        if (!email || !password) {
          setError('Please provide email and password.');
          setLoading(false);
          return;
        }
        await login(email, password);
        navigate('/datasets');
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Authentication failed. Please verify credentials.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  };

  const handleResetToSignIn = () => {
    setJoinSuccess(null);
    setMode('login');
    setError(null);
    setPassword('');
    setConfirmPassword('');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-brand-950 flex flex-col items-center justify-center p-4 relative">
      {/* Theme toggle on login screen */}
      <div className="absolute top-4 right-4">
        <button
          onClick={toggleTheme}
          aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          className="flex items-center space-x-1.5 p-2 rounded-lg border border-slate-700 bg-slate-800/80 text-amber-400 hover:bg-slate-700/80 transition-all text-xs font-medium shadow-sm backdrop-blur-sm"
        >
          {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-300" />}
          <span className="text-slate-200">{isDark ? 'Light' : 'Dark'}</span>
        </button>
      </div>

      <div className="max-w-md w-full bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden transition-colors">
        {/* Header */}
        <div className="bg-brand-600 p-8 text-center text-white relative">
          <div className="mx-auto w-12 h-12 bg-white/10 rounded-xl flex items-center justify-center mb-3 backdrop-blur-sm">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">AI Powered Inventory Management and Intelligence Copilot</h1>
          <p className="text-brand-100 text-xs sm:text-sm mt-1.5 leading-relaxed">
            Multi-tenant AI-powered inventory management, machine learning, demand forecasting, and decision intelligence.
          </p>
        </div>

        {/* 3 Authentication Choices */}
        <div className="flex border-b border-slate-200 dark:border-slate-800 text-xs sm:text-sm font-semibold">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setError(null);
              setJoinSuccess(null);
            }}
            className={`flex-1 py-3 text-center transition-colors border-b-2 ${
              mode === 'login'
                ? 'text-brand-600 dark:text-brand-400 border-brand-600 dark:border-brand-400 bg-brand-50/50 dark:bg-blue-950/40'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('register_owner');
              setError(null);
              setJoinSuccess(null);
            }}
            className={`flex-1 py-3 text-center transition-colors border-b-2 ${
              mode === 'register_owner'
                ? 'text-brand-600 dark:text-brand-400 border-brand-600 dark:border-brand-400 bg-brand-50/50 dark:bg-blue-950/40'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Register (Owner)
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('join_worker');
              setError(null);
              setJoinSuccess(null);
            }}
            className={`flex-1 py-3 text-center transition-colors border-b-2 ${
              mode === 'join_worker'
                ? 'text-brand-600 dark:text-brand-400 border-brand-600 dark:border-brand-400 bg-brand-50/50 dark:bg-blue-950/40'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Join (Worker)
          </button>
        </div>

        {/* Worker Join Request Confirmation Screen */}
        {joinSuccess ? (
          <div className="p-8 text-center space-y-4">
            <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto shadow-sm">
              <CheckCircle2 className="w-8 h-8" />
            </div>

            <div className="space-y-1">
              <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                Join Request Submitted!
              </h3>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Your request to join <span className="font-semibold text-brand-600 dark:text-brand-400">{joinSuccess.companyName}</span> has been sent to the workspace owner for review.
              </p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-xl border border-slate-200 dark:border-slate-700/80 text-xs text-slate-500 dark:text-slate-400 text-left space-y-1">
              <div className="font-semibold text-slate-700 dark:text-slate-200 flex items-center space-x-1.5">
                <Users className="w-4 h-4 text-brand-500" />
                <span>What happens next?</span>
              </div>
              <p>1. The workspace owner will review your application in Team Management.</p>
              <p>2. Once approved, you can log in immediately using <span className="font-mono text-slate-700 dark:text-slate-300">{joinSuccess.email}</span>.</p>
              <p>3. No further registration or email confirmation is required.</p>
            </div>

            <button
              type="button"
              onClick={handleResetToSignIn}
              className="w-full inline-flex items-center justify-center space-x-2 py-2.5 px-4 bg-brand-600 hover:bg-brand-700 text-white font-medium rounded-lg text-sm transition shadow-sm"
            >
              <span>Back to Sign In</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        ) : (
          /* Form */
          <form onSubmit={handleSubmit} className="p-8 space-y-4">
            {error && (
              <div className="p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-xl flex items-start space-x-2.5 text-sm text-red-700 dark:text-red-300">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {/* Mode-specific badge/info */}
            {mode === 'join_worker' && (
              <div className="p-3 bg-blue-50/70 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900/60 rounded-xl text-xs text-blue-700 dark:text-blue-300 flex items-start space-x-2">
                <Users className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <span>
                  Submit your details and target workspace slug. Access will be activated upon workspace owner approval.
                </span>
              </div>
            )}

            {/* Full Name (For Owner Registration and Worker Join) */}
            {(mode === 'register_owner' || mode === 'join_worker') && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Full Name
                </label>
                <div className="relative">
                  <UserIcon className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Jane Doe"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>
            )}

            {/* Workspace / Company Name (For Owner Registration Only) */}
            {mode === 'register_owner' && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Company / Workspace Name
                </label>
                <div className="relative">
                  <Building2 className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="Acme Supply Chain Corp"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>
            )}

            {/* Workspace Identifier / Slug (For Worker Join Only) */}
            {mode === 'join_worker' && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Target Workspace Slug or Name
                </label>
                <div className="relative">
                  <Building2 className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={workspaceSlug}
                    onChange={(e) => setWorkspaceSlug(e.target.value)}
                    placeholder="e.g. acme-supply-chain"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                  Obtain the workspace slug or name from your company administrator.
                </p>
              </div>
            )}

            {/* Email Address */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                Email Address
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  className="w-full pl-9 pr-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  className="w-full pl-9 pr-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>

            {/* Confirm Password (Worker Join Only) */}
            {mode === 'join_worker' && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••••••"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-brand-600 hover:bg-brand-700 text-white font-medium rounded-lg text-sm transition-colors shadow-sm disabled:opacity-50 mt-2"
            >
              {loading
                ? 'Processing...'
                : mode === 'register_owner'
                ? 'Create Owner Account & Workspace'
                : mode === 'join_worker'
                ? 'Submit Join Request'
                : 'Sign In'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

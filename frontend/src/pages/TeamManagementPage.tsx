import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { workspaceApi } from '../services/api';
import { WorkspaceMember, AddWorkerPayload, WorkspaceJoinRequest } from '../types';
import {
  Users,
  UserPlus,
  ShieldAlert,
  ShieldCheck,
  Crown,
  User,
  Search,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  X,
  Eye,
  EyeOff,
  Lock,
  ArrowRight,
  Mail,
  Calendar,
  Clock,
  Check,
  UserCheck,
  UserX,
} from 'lucide-react';

export const TeamManagementPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, activeCompany, refreshPendingRequestsCount } = useAuth();
  const isOwner = activeCompany?.role === 'OWNER';

  // Active Tab: 'members' | 'requests'
  const [activeTab, setActiveTab] = useState<'members' | 'requests'>('members');

  // Member list state
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'ALL' | 'OWNER' | 'WORKER'>('ALL');
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Join Requests state
  const [joinRequests, setJoinRequests] = useState<WorkspaceJoinRequest[]>([]);
  const [loadingRequests, setLoadingRequests] = useState(false);
  const [requestsSearch, setRequestsSearch] = useState('');

  // Approve / Reject Dialogs state
  const [approveDialog, setApproveDialog] = useState<{
    open: boolean;
    request: WorkspaceJoinRequest | null;
    isSubmitting: boolean;
    error: string | null;
  }>({
    open: false,
    request: null,
    isSubmitting: false,
    error: null,
  });

  const [rejectDialog, setRejectDialog] = useState<{
    open: boolean;
    request: WorkspaceJoinRequest | null;
    reason: string;
    isSubmitting: boolean;
    error: string | null;
  }>({
    open: false,
    request: null,
    reason: '',
    isSubmitting: false,
    error: null,
  });

  // Add Worker Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [formData, setFormData] = useState<AddWorkerPayload>({
    full_name: '',
    email: '',
    password: '',
    role: 'WORKER',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Role Confirmation Dialog state
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    member: WorkspaceMember | null;
    targetRole: 'OWNER' | 'WORKER';
    isSubmitting: boolean;
    error: string | null;
  }>({
    open: false,
    member: null,
    targetRole: 'WORKER',
    isSubmitting: false,
    error: null,
  });

  // Close modal/dialog on Escape key press
  useEffect(() => {
    const isAnyModalOpen =
      showAddModal || confirmDialog.open || approveDialog.open || rejectDialog.open;
    if (!isAnyModalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showAddModal && !isSubmitting) setShowAddModal(false);
        if (confirmDialog.open && !confirmDialog.isSubmitting)
          setConfirmDialog((prev) => ({ ...prev, open: false }));
        if (approveDialog.open && !approveDialog.isSubmitting)
          setApproveDialog((prev) => ({ ...prev, open: false }));
        if (rejectDialog.open && !rejectDialog.isSubmitting)
          setRejectDialog((prev) => ({ ...prev, open: false }));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    showAddModal,
    confirmDialog.open,
    approveDialog.open,
    rejectDialog.open,
    isSubmitting,
    confirmDialog.isSubmitting,
    approveDialog.isSubmitting,
    rejectDialog.isSubmitting,
  ]);

  // Lock body scroll while modal or dialog is open
  useEffect(() => {
    const isAnyOpen =
      showAddModal || confirmDialog.open || approveDialog.open || rejectDialog.open;
    if (!isAnyOpen) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [showAddModal, confirmDialog.open, approveDialog.open, rejectDialog.open]);

  const fetchMembers = async () => {
    if (!activeCompany || !isOwner) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await workspaceApi.getMembers();
      setMembers(data);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load workspace members.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const fetchRequests = async () => {
    if (!activeCompany || !isOwner) return;
    setLoadingRequests(true);
    try {
      const data = await workspaceApi.getJoinRequests('PENDING');
      setJoinRequests(data);
      if (refreshPendingRequestsCount) {
        refreshPendingRequestsCount();
      }
    } catch (err: any) {
      console.error('Failed to load join requests:', err);
    } finally {
      setLoadingRequests(false);
    }
  };

  const refreshAll = async () => {
    await Promise.all([fetchMembers(), fetchRequests()]);
  };

  useEffect(() => {
    refreshAll();
  }, [activeCompany?.id, isOwner]);

  // Derived counts
  const totalCount = members.length;
  const ownerCount = members.filter((m) => m.role === 'OWNER').length;
  const workerCount = members.filter((m) => m.role === 'WORKER').length;
  const activeCount = members.filter((m) => m.is_active !== false).length;

  // Filtered members list
  const filteredMembers = members.filter((m) => {
    const matchesSearch =
      m.full_name.toLowerCase().includes(search.toLowerCase()) ||
      m.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === 'ALL' || m.role === roleFilter;
    return matchesSearch && matchesRole;
  });

  // Filtered requests list
  const filteredRequests = joinRequests.filter((r) => {
    const matches =
      r.full_name.toLowerCase().includes(requestsSearch.toLowerCase()) ||
      r.email.toLowerCase().includes(requestsSearch.toLowerCase());
    return matches;
  });

  // Handle Add Worker Submit (Path A)
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Client-side validations
    const trimmedName = formData.full_name.trim();
    const trimmedEmail = formData.email.trim();
    if (trimmedName.length < 2) {
      setFormError('Full name must be at least 2 characters long.');
      return;
    }
    if (!trimmedEmail || !trimmedEmail.includes('@')) {
      setFormError('Please enter a valid email address.');
      return;
    }
    if (!formData.password || formData.password.length < 6) {
      setFormError('Temporary password must be at least 6 characters.');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload: AddWorkerPayload = {
        full_name: trimmedName,
        email: trimmedEmail,
        password: formData.password,
        role: 'WORKER',
      };

      const newMember = await workspaceApi.addWorker(payload);

      // Clean up sensitive state immediately
      setFormData({ full_name: '', email: '', password: '', role: 'WORKER' });
      setShowAddModal(false);
      setSuccessBanner(
        `Successfully added ${newMember.full_name} (${newMember.email}) as a WORKER to ${activeCompany?.name}. They can log in immediately.`
      );

      // Refresh roster
      await refreshAll();
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to add team member. Please check details and retry.';
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Role Change Confirmation
  const promptRoleChange = (member: WorkspaceMember, targetRole: 'OWNER' | 'WORKER') => {
    setConfirmDialog({
      open: true,
      member,
      targetRole,
      isSubmitting: false,
      error: null,
    });
  };

  // Execute Role Change
  const handleConfirmRoleChange = async () => {
    if (!confirmDialog.member) return;

    setConfirmDialog((prev) => ({ ...prev, isSubmitting: true, error: null }));
    try {
      const updated = await workspaceApi.updateRole(
        confirmDialog.member.id,
        confirmDialog.targetRole
      );

      setSuccessBanner(`Updated ${updated.full_name}'s role to ${updated.role}.`);
      setConfirmDialog({
        open: false,
        member: null,
        targetRole: 'WORKER',
        isSubmitting: false,
        error: null,
      });

      // Refresh list
      await refreshAll();
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to update member role.';
      setConfirmDialog((prev) => ({ ...prev, isSubmitting: false, error: msg }));
    }
  };

  // Approve Join Request (Path B)
  const handleApproveConfirm = async () => {
    if (!approveDialog.request) return;
    setApproveDialog((prev) => ({ ...prev, isSubmitting: true, error: null }));
    try {
      await workspaceApi.approveJoinRequest(approveDialog.request.id);
      const reqName = approveDialog.request.full_name;
      const reqEmail = approveDialog.request.email;
      setApproveDialog({ open: false, request: null, isSubmitting: false, error: null });
      setSuccessBanner(
        `Join request for ${reqName} (${reqEmail}) approved successfully! Worker has been added to the workspace roster.`
      );
      await refreshAll();
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to approve join request.';
      setApproveDialog((prev) => ({ ...prev, isSubmitting: false, error: msg }));
    }
  };

  // Reject Join Request (Path B)
  const handleRejectConfirm = async () => {
    if (!rejectDialog.request) return;
    setRejectDialog((prev) => ({ ...prev, isSubmitting: true, error: null }));
    try {
      await workspaceApi.rejectJoinRequest(rejectDialog.request.id, rejectDialog.reason);
      const reqName = rejectDialog.request.full_name;
      setRejectDialog({ open: false, request: null, reason: '', isSubmitting: false, error: null });
      setSuccessBanner(`Join request for ${reqName} was rejected.`);
      await refreshAll();
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to reject join request.';
      setRejectDialog((prev) => ({ ...prev, isSubmitting: false, error: msg }));
    }
  };

  // Helper to get initials
  const getInitials = (name: string) => {
    return name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((n) => n[0].toUpperCase())
      .join('');
  };

  // Permission Denied View for Workers or users without active company
  if (!activeCompany) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-8 text-center space-y-4 shadow-sm">
          <ShieldAlert className="h-12 w-12 text-amber-500 mx-auto" />
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100">No Active Workspace Selected</h2>
          <p className="text-slate-600 dark:text-slate-400 max-w-md mx-auto text-sm">
            Please select an active workspace from the top navigation bar to manage team members.
          </p>
          <button
            onClick={() => navigate('/datasets')}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition font-medium text-sm"
          >
            <span>Go to Datasets</span>
          </button>
        </div>
      </div>
    );
  }

  if (!isOwner) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-10 text-center space-y-4 shadow-sm">
          <div className="h-16 w-16 bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400 rounded-2xl flex items-center justify-center mx-auto shadow-inner">
            <ShieldAlert className="h-8 w-8" />
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">Owner Access Required</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto">
              Team management is restricted to workspace owners. Workers have access to datasets, model training, and predictions, but cannot manage team rosters.
            </p>
          </div>
          <div className="pt-2">
            <button
              onClick={() => navigate('/datasets')}
              className="inline-flex items-center space-x-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition font-medium text-sm shadow-sm"
            >
              <span>Return to Workspace Overview</span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold text-brand-600 dark:text-brand-400 uppercase tracking-wider mb-1">
            <Users className="h-3.5 w-3.5" />
            <span>Workspace Administration</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">Team Management</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Manage authorized workers, review registration requests, and configure access for{' '}
            <span className="font-semibold text-slate-700 dark:text-slate-300">{activeCompany.name}</span>.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={refreshAll}
            disabled={loading || loadingRequests}
            className="p-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-lg transition shadow-sm disabled:opacity-50"
            title="Refresh All"
          >
            <RefreshCw
              className={`h-4 w-4 ${loading || loadingRequests ? 'animate-spin text-brand-600 dark:text-brand-400' : ''}`}
            />
          </button>

          <button
            onClick={() => {
              setFormError(null);
              setShowAddModal(true);
            }}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition font-medium text-sm shadow-sm"
          >
            <UserPlus className="h-4 w-4" />
            <span>Add Worker</span>
          </button>
        </div>
      </div>

      {/* Success Banner */}
      {successBanner && (
        <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 px-4 py-3 rounded-xl flex items-center justify-between text-sm shadow-sm animate-in fade-in duration-200">
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
            <span>{successBanner}</span>
          </div>
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-emerald-600 dark:text-emerald-400 hover:text-emerald-800 dark:hover:text-emerald-200 p-1 rounded-md transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Error Alert */}
      {error && (
        <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-300 px-4 py-3 rounded-xl flex items-center justify-between text-sm shadow-sm">
          <div className="flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchMembers}
            className="text-xs bg-red-100 dark:bg-red-900/60 hover:bg-red-200 dark:hover:bg-red-800/80 text-red-700 dark:text-red-200 px-2.5 py-1 rounded-md font-medium transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm flex items-center space-x-4">
          <div className="h-12 w-12 rounded-xl bg-brand-50 dark:bg-blue-950/60 text-brand-600 dark:text-blue-400 flex items-center justify-center font-bold">
            <Users className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{totalCount}</div>
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400">Total Team Members</div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm flex items-center space-x-4">
          <div className="h-12 w-12 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center font-bold">
            <Crown className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{ownerCount}</div>
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400">Workspace Owners</div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm flex items-center space-x-4">
          <div className="h-12 w-12 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 flex items-center justify-center font-bold">
            <User className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{workerCount}</div>
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400">Workspace Workers</div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm flex items-center space-x-4">
          <div className="h-12 w-12 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center font-bold">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{activeCount}</div>
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400">Active Accounts</div>
          </div>
        </div>

        {/* Pending Requests KPI */}
        <div
          onClick={() => setActiveTab('requests')}
          className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm flex items-center space-x-4 cursor-pointer hover:border-amber-400 dark:hover:border-amber-500 transition"
          title="Click to view pending join requests"
        >
          <div className="h-12 w-12 rounded-xl bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center font-bold">
            <Clock className="h-6 w-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <span>{joinRequests.length}</span>
              {joinRequests.length > 0 && (
                <span className="text-[10px] bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-300 px-2 py-0.5 rounded-full font-bold">
                  Action
                </span>
              )}
            </div>
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400">Pending Requests</div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-200 dark:border-slate-800 space-x-8">
        <button
          onClick={() => setActiveTab('members')}
          className={`pb-3 text-sm font-semibold border-b-2 transition flex items-center space-x-2 ${
            activeTab === 'members'
              ? 'border-brand-600 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <Users className="h-4 w-4" />
          <span>Active Team Members ({totalCount})</span>
        </button>

        <button
          onClick={() => setActiveTab('requests')}
          className={`pb-3 text-sm font-semibold border-b-2 transition flex items-center space-x-2 ${
            activeTab === 'requests'
              ? 'border-brand-600 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <Clock className="h-4 w-4" />
          <span>Pending Join Requests</span>
          {joinRequests.length > 0 && (
            <span className="px-2 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-300 rounded-full font-bold">
              {joinRequests.length}
            </span>
          )}
        </button>
      </div>

      {/* TAB 1: MEMBERS */}
      {activeTab === 'members' && (
        <div className="space-y-4">
          {/* Filter and Search Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white dark:bg-slate-900 p-3 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search team member by name or email..."
                className="w-full pl-9 pr-3 py-1.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 transition"
              />
            </div>

            <div className="flex items-center space-x-2">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Role:</span>
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value as any)}
                className="text-sm bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-1.5 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="ALL">All Roles ({totalCount})</option>
                <option value="OWNER">Owners ({ownerCount})</option>
                <option value="WORKER">Workers ({workerCount})</option>
              </select>
            </div>
          </div>

          {/* Members Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden">
            {loading ? (
              <div className="p-12 text-center text-slate-400 text-sm flex flex-col items-center justify-center space-y-3">
                <RefreshCw className="h-6 w-6 animate-spin text-brand-600 dark:text-brand-400" />
                <span>Loading workspace team members...</span>
              </div>
            ) : filteredMembers.length === 0 ? (
              <div className="p-12 text-center text-slate-500 dark:text-slate-400 space-y-3">
                <Users className="h-10 w-10 text-slate-300 dark:text-slate-600 mx-auto" />
                <div className="font-semibold text-slate-700 dark:text-slate-300">No team members match your criteria</div>
                <p className="text-xs text-slate-400 dark:text-slate-500 max-w-sm mx-auto">
                  {search
                    ? `No members found matching "${search}". Try clearing your search term.`
                    : 'No members have been added to this workspace yet.'}
                </p>
                {search && (
                  <button
                    onClick={() => setSearch('')}
                    className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Clear Search
                  </button>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto custom-scrollbar">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-700 text-xs uppercase font-semibold">
                    <tr>
                      <th className="px-6 py-3.5">Member</th>
                      <th className="px-6 py-3.5">Role</th>
                      <th className="px-6 py-3.5">Account Status</th>
                      <th className="px-6 py-3.5">Added Date</th>
                      <th className="px-6 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {filteredMembers.map((member) => {
                      const isCurrentUser = member.user_id === user?.id;
                      const isSoleOwner = member.role === 'OWNER' && ownerCount <= 1;

                      return (
                        <tr key={member.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors">
                          {/* Member Info */}
                          <td className="px-6 py-4">
                            <div className="flex items-center space-x-3">
                              <div
                                className={`h-10 w-10 rounded-full flex items-center justify-center text-xs font-bold text-white shadow-sm flex-shrink-0 ${
                                  member.role === 'OWNER'
                                    ? 'bg-gradient-to-tr from-indigo-600 to-brand-600'
                                    : 'bg-gradient-to-tr from-slate-600 to-slate-400'
                                }`}
                              >
                                {getInitials(member.full_name || member.email)}
                              </div>
                              <div>
                                <div className="font-semibold text-slate-900 dark:text-slate-100 flex items-center space-x-1.5">
                                  <span>{member.full_name}</span>
                                  {isCurrentUser && (
                                    <span className="text-[10px] bg-brand-100 dark:bg-blue-950/60 text-brand-700 dark:text-blue-300 px-1.5 py-0.2 rounded font-semibold uppercase">
                                      You
                                    </span>
                                  )}
                                </div>
                                <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center space-x-1 mt-0.5">
                                  <Mail className="h-3 w-3 text-slate-400" />
                                  <span>{member.email}</span>
                                </div>
                              </div>
                            </div>
                          </td>

                          {/* Role Badge */}
                          <td className="px-6 py-4">
                            {member.role === 'OWNER' ? (
                              <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                                <Crown className="h-3 w-3" />
                                <span>Owner</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                                <User className="h-3 w-3 text-slate-400" />
                                <span>Worker</span>
                              </span>
                            )}
                          </td>

                          {/* Account Status */}
                          <td className="px-6 py-4">
                            <span className="inline-flex items-center space-x-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                              <span>Active</span>
                            </span>
                          </td>

                          {/* Added Date */}
                          <td className="px-6 py-4 text-xs text-slate-500 dark:text-slate-400">
                            <div className="flex items-center space-x-1">
                              <Calendar className="h-3 w-3 text-slate-400" />
                              <span>{new Date(member.created_at).toLocaleDateString()}</span>
                            </div>
                          </td>

                          {/* Actions */}
                          <td className="px-6 py-4 text-right">
                            {isCurrentUser ? (
                              <span className="text-xs text-slate-400 dark:text-slate-500 italic">Current Session</span>
                            ) : isSoleOwner ? (
                              <span
                                className="text-xs text-slate-400 dark:text-slate-500 italic"
                                title="At least one owner must remain in the workspace"
                              >
                                Sole Owner
                              </span>
                            ) : (
                              <button
                                type="button"
                                onClick={() =>
                                  promptRoleChange(
                                    member,
                                    member.role === 'OWNER' ? 'WORKER' : 'OWNER'
                                  )
                                }
                                className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:text-brand-800 dark:hover:text-brand-300 underline"
                              >
                                {member.role === 'OWNER' ? 'Demote to Worker' : 'Promote to Owner'}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: PENDING JOIN REQUESTS */}
      {activeTab === 'requests' && (
        <div className="space-y-4">
          {/* Requests Search Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white dark:bg-slate-900 p-3 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={requestsSearch}
                onChange={(e) => setRequestsSearch(e.target.value)}
                placeholder="Search requests by applicant name or email..."
                className="w-full pl-9 pr-3 py-1.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white dark:focus:bg-slate-900 transition"
              />
            </div>

            <div className="text-xs text-slate-500 dark:text-slate-400">
              Showing <span className="font-bold text-slate-800 dark:text-slate-200">{filteredRequests.length}</span> pending applications
            </div>
          </div>

          {/* Requests Table */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm overflow-hidden">
            {loadingRequests ? (
              <div className="p-12 text-center text-slate-400 text-sm flex flex-col items-center justify-center space-y-3">
                <RefreshCw className="h-6 w-6 animate-spin text-brand-600 dark:text-brand-400" />
                <span>Loading pending join requests...</span>
              </div>
            ) : filteredRequests.length === 0 ? (
              <div className="p-12 text-center text-slate-500 dark:text-slate-400 space-y-3">
                <Clock className="h-10 w-10 text-slate-300 dark:text-slate-600 mx-auto" />
                <div className="font-semibold text-slate-700 dark:text-slate-300">No pending join requests</div>
                <p className="text-xs text-slate-400 dark:text-slate-500 max-w-sm mx-auto">
                  {requestsSearch
                    ? `No applications found matching "${requestsSearch}".`
                    : 'All registration requests for this workspace have been reviewed.'}
                </p>
                {requestsSearch && (
                  <button
                    onClick={() => setRequestsSearch('')}
                    className="text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Clear Search
                  </button>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto custom-scrollbar">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-b border-slate-200 dark:border-slate-700 text-xs uppercase font-semibold">
                    <tr>
                      <th className="px-6 py-3.5">Applicant</th>
                      <th className="px-6 py-3.5">Target Workspace</th>
                      <th className="px-6 py-3.5">Submitted Date</th>
                      <th className="px-6 py-3.5">Status</th>
                      <th className="px-6 py-3.5 text-right">Review Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {filteredRequests.map((req) => (
                      <tr key={req.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors">
                        {/* Applicant Info */}
                        <td className="px-6 py-4">
                          <div className="flex items-center space-x-3">
                            <div className="h-10 w-10 rounded-full flex items-center justify-center text-xs font-bold text-white shadow-sm flex-shrink-0 bg-gradient-to-tr from-amber-600 to-amber-500">
                              {getInitials(req.full_name || req.email)}
                            </div>
                            <div>
                              <div className="font-semibold text-slate-900 dark:text-slate-100">
                                {req.full_name}
                              </div>
                              <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center space-x-1 mt-0.5">
                                <Mail className="h-3 w-3 text-slate-400" />
                                <span>{req.email}</span>
                              </div>
                            </div>
                          </div>
                        </td>

                        {/* Target Workspace */}
                        <td className="px-6 py-4">
                          <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                            {req.company_name}
                          </span>
                          {req.company_slug && (
                            <span className="block text-[11px] font-mono text-slate-400">
                              {req.company_slug}
                            </span>
                          )}
                        </td>

                        {/* Submitted Date */}
                        <td className="px-6 py-4 text-xs text-slate-500 dark:text-slate-400">
                          <div className="flex items-center space-x-1">
                            <Calendar className="h-3 w-3 text-slate-400" />
                            <span>{new Date(req.created_at).toLocaleString()}</span>
                          </div>
                        </td>

                        {/* Status */}
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                            <Clock className="h-3 w-3" />
                            <span>Pending Review</span>
                          </span>
                        </td>

                        {/* Review Actions */}
                        <td className="px-6 py-4 text-right space-x-2 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() =>
                              setApproveDialog({
                                open: true,
                                request: req,
                                isSubmitting: false,
                                error: null,
                              })
                            }
                            className="inline-flex items-center space-x-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition"
                            title="Approve worker join request"
                          >
                            <Check className="h-3.5 w-3.5" />
                            <span>Approve</span>
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              setRejectDialog({
                                open: true,
                                request: req,
                                reason: '',
                                isSubmitting: false,
                                error: null,
                              })
                            }
                            className="inline-flex items-center space-x-1 px-3 py-1.5 border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400 rounded-lg text-xs font-semibold transition"
                            title="Reject worker join request"
                          >
                            <X className="h-3.5 w-3.5" />
                            <span>Reject</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODAL 1: Add Worker Modal (Path A) */}
      {showAddModal &&
        createPortal(
          <div
            className="fixed inset-0 m-0 p-4 sm:p-6 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget && !isSubmitting) setShowAddModal(false);
            }}
            role="dialog"
            aria-modal="true"
          >
            <div
              className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Add Team Worker</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Directly create an active worker account for <strong className="text-slate-700 dark:text-slate-300">{activeCompany.name}</strong>.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (!isSubmitting) setShowAddModal(false);
                  }}
                  disabled={isSubmitting}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 p-1 rounded-lg transition"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <form onSubmit={handleAddSubmit} className="p-6 space-y-4">
                {formError && (
                  <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 rounded-xl text-xs flex items-start space-x-2">
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                    <span>{formError}</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Full Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.full_name}
                    onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                    placeholder="e.g. Alex Johnson"
                    disabled={isSubmitting}
                    className="w-full px-3.5 py-2 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-50 dark:disabled:bg-slate-900"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Work Email <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="e.g. alex@company.com"
                    disabled={isSubmitting}
                    className="w-full px-3.5 py-2 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-50 dark:disabled:bg-slate-900"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Initial Password <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required
                      minLength={6}
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      placeholder="Min 6 characters"
                      disabled={isSubmitting}
                      className="w-full px-3.5 py-2 pr-10 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-slate-50 dark:disabled:bg-slate-900"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      tabIndex={-1}
                      className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                    The worker can immediately sign in with this password without waiting for approval.
                  </p>
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300">
                  <span className="font-semibold text-slate-800 dark:text-slate-200 block mb-0.5">Assigned Role: WORKER</span>
                  Newly added team members start with the Worker role. Owners can promote workers to Owner from the team roster if needed.
                </div>

                <div className="pt-3 flex items-center justify-end space-x-3 border-t border-slate-100 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    disabled={isSubmitting}
                    className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg text-sm font-medium transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="inline-flex items-center space-x-2 px-5 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
                  >
                    {isSubmitting && <RefreshCw className="h-4 w-4 animate-spin" />}
                    <span>{isSubmitting ? 'Adding Worker...' : 'Create Worker'}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body
        )}

      {/* MODAL 2: Approve Request Confirmation Modal */}
      {approveDialog.open &&
        approveDialog.request &&
        createPortal(
          <div
            className="fixed inset-0 m-0 p-4 sm:p-6 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget && !approveDialog.isSubmitting)
                setApproveDialog((prev) => ({ ...prev, open: false }));
            }}
            role="dialog"
            aria-modal="true"
          >
            <div
              className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4 my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center space-x-3">
                <div className="h-12 w-12 rounded-xl bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center flex-shrink-0">
                  <UserCheck className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                    Approve Worker Join Request
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Grant workspace access to applicant
                  </p>
                </div>
              </div>

              {approveDialog.error && (
                <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 rounded-xl text-xs flex items-start space-x-2">
                  <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <span>{approveDialog.error}</span>
                </div>
              )}

              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                Are you sure you want to approve{' '}
                <strong className="text-slate-900 dark:text-slate-100">
                  {approveDialog.request.full_name}
                </strong>{' '}
                (<span className="font-mono text-xs">{approveDialog.request.email}</span>)?
              </p>

              <div className="p-3 bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 rounded-xl text-xs text-emerald-800 dark:text-emerald-300 space-y-1">
                <div className="font-semibold flex items-center space-x-1">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>Immediate Access Granted</span>
                </div>
                <p>
                  Upon approval, this worker will immediately be assigned the WORKER role in{' '}
                  <strong>{activeCompany.name}</strong> and can sign in to view datasets, run model experiments, and generate predictions.
                </p>
              </div>

              <div className="pt-2 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setApproveDialog({ open: false, request: null, isSubmitting: false, error: null })}
                  disabled={approveDialog.isSubmitting}
                  className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg text-sm font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleApproveConfirm}
                  disabled={approveDialog.isSubmitting}
                  className="inline-flex items-center space-x-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
                >
                  {approveDialog.isSubmitting && <RefreshCw className="h-4 w-4 animate-spin" />}
                  <span>{approveDialog.isSubmitting ? 'Approving...' : 'Approve & Grant Access'}</span>
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}

      {/* MODAL 3: Reject Request Confirmation Modal */}
      {rejectDialog.open &&
        rejectDialog.request &&
        createPortal(
          <div
            className="fixed inset-0 m-0 p-4 sm:p-6 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget && !rejectDialog.isSubmitting)
                setRejectDialog((prev) => ({ ...prev, open: false }));
            }}
            role="dialog"
            aria-modal="true"
          >
            <div
              className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4 my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center space-x-3">
                <div className="h-12 w-12 rounded-xl bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400 flex items-center justify-center flex-shrink-0">
                  <UserX className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                    Reject Worker Join Request
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Decline applicant membership
                  </p>
                </div>
              </div>

              {rejectDialog.error && (
                <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 rounded-xl text-xs flex items-start space-x-2">
                  <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <span>{rejectDialog.error}</span>
                </div>
              )}

              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                Reject membership request for{' '}
                <strong className="text-slate-900 dark:text-slate-100">
                  {rejectDialog.request.full_name}
                </strong>{' '}
                (<span className="font-mono text-xs">{rejectDialog.request.email}</span>)? They will not be granted access to this workspace.
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Rejection Reason (Optional)
                </label>
                <textarea
                  rows={2}
                  value={rejectDialog.reason}
                  onChange={(e) => setRejectDialog({ ...rejectDialog, reason: e.target.value })}
                  placeholder="e.g. Unrecognized email or role requirements unfulfilled."
                  disabled={rejectDialog.isSubmitting}
                  className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50"
                />
              </div>

              <div className="pt-2 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setRejectDialog({ open: false, request: null, reason: '', isSubmitting: false, error: null })}
                  disabled={rejectDialog.isSubmitting}
                  className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg text-sm font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleRejectConfirm}
                  disabled={rejectDialog.isSubmitting}
                  className="inline-flex items-center space-x-2 px-5 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
                >
                  {rejectDialog.isSubmitting && <RefreshCw className="h-4 w-4 animate-spin" />}
                  <span>{rejectDialog.isSubmitting ? 'Rejecting...' : 'Confirm Rejection'}</span>
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}

      {/* MODAL 4: Role Confirmation Dialog */}
      {confirmDialog.open &&
        confirmDialog.member &&
        createPortal(
          <div
            className="fixed inset-0 m-0 p-4 sm:p-6 z-50 flex items-center justify-center overflow-y-auto bg-slate-900/60 dark:bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={(e) => {
              if (e.target === e.currentTarget && !confirmDialog.isSubmitting)
                setConfirmDialog((prev) => ({ ...prev, open: false }));
            }}
            role="dialog"
            aria-modal="true"
          >
            <div
              className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4 my-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center space-x-3">
                <div
                  className={`h-12 w-12 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    confirmDialog.targetRole === 'OWNER'
                      ? 'bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                      : 'bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400'
                  }`}
                >
                  {confirmDialog.targetRole === 'OWNER' ? (
                    <ShieldCheck className="h-6 w-6" />
                  ) : (
                    <ShieldAlert className="h-6 w-6" />
                  )}
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                    {confirmDialog.targetRole === 'OWNER' ? 'Promote to Owner' : 'Demote to Worker'}
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Modify workspace member permissions
                  </p>
                </div>
              </div>

              {confirmDialog.error && (
                <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 rounded-xl text-xs flex items-start space-x-2">
                  <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <span>{confirmDialog.error}</span>
                </div>
              )}

              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                {confirmDialog.targetRole === 'OWNER' ? (
                  <>
                    Are you sure you want to promote{' '}
                    <strong className="text-slate-900 dark:text-slate-100">{confirmDialog.member.full_name}</strong> to{' '}
                    <strong className="text-indigo-700 dark:text-indigo-400">Workspace Owner</strong>? They will be granted full administrative control, including the ability to add and remove workers and modify workspace settings.
                  </>
                ) : (
                  <>
                    Are you sure you want to demote{' '}
                    <strong className="text-slate-900 dark:text-slate-100">{confirmDialog.member.full_name}</strong> to{' '}
                    <strong className="text-slate-700 dark:text-slate-300">Worker</strong>? They will lose access to team management and administration, but retain access to datasets, model training, and predictions.
                  </>
                )}
              </p>

              <div className="pt-2 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() =>
                    setConfirmDialog({
                      open: false,
                      member: null,
                      targetRole: 'WORKER',
                      isSubmitting: false,
                      error: null,
                    })
                  }
                  disabled={confirmDialog.isSubmitting}
                  className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg text-sm font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmRoleChange}
                  disabled={confirmDialog.isSubmitting}
                  className={`inline-flex items-center space-x-2 px-5 py-2 text-white rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50 ${
                    confirmDialog.targetRole === 'OWNER'
                      ? 'bg-indigo-600 hover:bg-indigo-700'
                      : 'bg-amber-600 hover:bg-amber-700'
                  }`}
                >
                  {confirmDialog.isSubmitting && <RefreshCw className="h-4 w-4 animate-spin" />}
                  <span>
                    {confirmDialog.isSubmitting
                      ? 'Updating...'
                      : confirmDialog.targetRole === 'OWNER'
                      ? 'Confirm Promotion'
                      : 'Confirm Demotion'}
                  </span>
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
};

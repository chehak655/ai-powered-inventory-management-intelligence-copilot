import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { User, Company } from '../types';
import { authApi, workspaceApi } from '../services/api';

interface AuthContextType {
  user: User | null;
  companies: Company[];
  activeCompany: Company | null;
  setActiveCompany: (company: Company) => void;
  pendingRequestsCount: number;
  refreshPendingRequestsCount: () => Promise<void>;
  login: (email: string, pass: string) => Promise<void>;
  register: (email: string, pass: string, name: string, companyName: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [activeCompany, setActiveCompanyState] = useState<Company | null>(null);
  const [pendingRequestsCount, setPendingRequestsCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);

  // Synchronize pending requests count for workspace owners
  const refreshPendingRequestsCount = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token || !activeCompany || activeCompany.role !== 'OWNER') {
      setPendingRequestsCount(0);
      return;
    }
    try {
      const data = await workspaceApi.getJoinRequests('PENDING');
      if (Array.isArray(data)) {
        const count = data.filter((r) => r.status === 'PENDING').length;
        setPendingRequestsCount(count);
      } else {
        setPendingRequestsCount(0);
      }
    } catch (err) {
      // Do not display fabricated count on network or authorization failure
      setPendingRequestsCount(0);
    }
  }, [activeCompany?.id, activeCompany?.role]);

  // Synchronize on active workspace changes or role changes
  useEffect(() => {
    refreshPendingRequestsCount();
  }, [refreshPendingRequestsCount]);

  // Background timer (every 30s) and window focus re-synchronization
  useEffect(() => {
    if (!activeCompany || activeCompany.role !== 'OWNER') {
      setPendingRequestsCount(0);
      return;
    }

    const handleFocus = () => {
      refreshPendingRequestsCount();
    };

    window.addEventListener('focus', handleFocus);
    const intervalTimer = setInterval(() => {
      refreshPendingRequestsCount();
    }, 30000);

    return () => {
      window.removeEventListener('focus', handleFocus);
      clearInterval(intervalTimer);
    };
  }, [activeCompany?.id, activeCompany?.role, refreshPendingRequestsCount]);

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const data = await authApi.getMe();
        setUser(data.user);
        setCompanies(data.companies);

        const savedCompanyId = localStorage.getItem('active_company_id');
        const matched = data.companies.find((c) => c.id === savedCompanyId);
        if (matched) {
          setActiveCompanyState(matched);
        } else if (data.companies.length > 0) {
          setActiveCompanyState(data.companies[0]);
          localStorage.setItem('active_company_id', data.companies[0].id);
        }
      } catch (err) {
        localStorage.removeItem('token');
        localStorage.removeItem('active_company_id');
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  const setActiveCompany = (company: Company) => {
    setActiveCompanyState(company);
    localStorage.setItem('active_company_id', company.id);
  };

  const login = async (email: string, pass: string) => {
    const data = await authApi.login(email, pass);
    localStorage.setItem('token', data.access_token);
    setUser(data.user);
    setCompanies(data.companies);
    if (data.companies.length > 0) {
      setActiveCompany(data.companies[0]);
    }
  };

  const register = async (email: string, pass: string, name: string, companyName: string) => {
    const data = await authApi.register(email, pass, name, companyName);
    localStorage.setItem('token', data.access_token);
    setUser(data.user);
    setCompanies(data.companies);
    if (data.companies.length > 0) {
      setActiveCompany(data.companies[0]);
    }
  };

  const logout = () => {
    authApi.logout().catch(() => {});
    localStorage.removeItem('token');
    localStorage.removeItem('active_company_id');
    setUser(null);
    setCompanies([]);
    setActiveCompanyState(null);
    setPendingRequestsCount(0);
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        companies,
        activeCompany,
        setActiveCompany,
        pendingRequestsCount,
        refreshPendingRequestsCount,
        login,
        register,
        logout,
        loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

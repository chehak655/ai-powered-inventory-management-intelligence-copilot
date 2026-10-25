import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { AppLayout } from './components/layout/AppLayout';
import { Login } from './pages/Login';
import { DatasetsPage } from './pages/DatasetsPage';
import { DatasetDetailPage } from './pages/DatasetDetailPage';
import { ModelLabPage } from './pages/ModelLabPage';
import { ModelRegistryPage } from './pages/ModelRegistryPage';
import { PredictionsPage } from './pages/PredictionsPage';
import { InventoryPage } from './pages/InventoryPage';
import { CopilotPage } from './pages/CopilotPage';
import { TeamManagementPage } from './pages/TeamManagementPage';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 text-slate-500 dark:text-slate-400 text-sm">
        Authenticating workspace session...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/datasets" replace />} />
              <Route path="datasets" element={<DatasetsPage />} />
              <Route path="datasets/:id" element={<DatasetDetailPage />} />
              <Route path="models" element={<ModelLabPage />} />
              <Route path="registry" element={<ModelRegistryPage />} />
              <Route path="predictions" element={<PredictionsPage />} />
              <Route path="inventory" element={<InventoryPage />} />
              <Route path="copilot" element={<CopilotPage />} />
              <Route path="team" element={<TeamManagementPage />} />
              <Route path="*" element={<Navigate to="/datasets" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};

export default App;

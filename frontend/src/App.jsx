import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/Layout';
import CampaignDetail from './pages/CampaignDetail';
import Inboxes from './pages/Inboxes';
import Schedule from './pages/Schedule';
import Settings from './pages/Settings';
import Analytics from './pages/Analytics';
import Unibox from './pages/Unibox';
import DeliverabilityTips from './pages/DeliverabilityTips';
import SystemHealth from './pages/SystemHealth';
import Leads from './pages/Leads';
import LeadDetail from './pages/LeadDetail';
import Notifications from './pages/Notifications';
import Login from './pages/Login';
import Templates from './pages/Templates';
import OutreachQueue from './pages/OutreachQueue';
import Projects from './pages/Projects';
import AddProject from './pages/AddProject';
import { api } from './api';
import { AuthProvider, useAuth } from './context/AuthContext';
import SplashScreen from './components/SplashScreen';
import { DarkModeProvider } from './context/DarkModeContext';
import { SystemHealthProvider } from './context/SystemHealthContext';
import { NotificationsProvider } from './context/NotificationsContext';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <SplashScreen />;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function AppRoutes() {
  const { user, loading } = useAuth();

  // Register this browser's IP as a known IP (auto-expires after 1 week)
  useEffect(() => {
    if (user) {
      api.post('/settings/known-ips/heartbeat', {}).catch(() => {});
    }
  }, [user]);

  if (loading) {
    return <SplashScreen />;
  }

  return (
    <Routes>
      <Route path="/login" element={
        user ? <Navigate to="/" replace /> : <Login />
      } />
      <Route path="/*" element={
        <ProtectedRoute>
          <Layout>
            <Routes>
              <Route path="/" element={<Navigate to="/projects" replace />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/projects/new" element={<AddProject />} />
              <Route path="/projects/:id" element={<CampaignDetail />} />
              <Route path="/contacts" element={<Leads />} />
              <Route path="/contacts/:id" element={<LeadDetail />} />
              <Route path="/templates" element={<Templates />} />
              <Route path="/outreach" element={<OutreachQueue />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/system-health" element={<SystemHealth />} />
              <Route path="/notifications" element={<Notifications />} />
              <Route path="/deliverability-tips" element={<DeliverabilityTips />} />
              <Route path="*" element={<Navigate to="/projects" replace />} />
            </Routes>
          </Layout>
        </ProtectedRoute>
      } />
    </Routes>
  );
}

export default function App() {
  return (
    <DarkModeProvider>
      <AuthProvider>
        <SystemHealthProvider>
          <NotificationsProvider>
            <AppRoutes />
          </NotificationsProvider>
        </SystemHealthProvider>
      </AuthProvider>
    </DarkModeProvider>
  );
}

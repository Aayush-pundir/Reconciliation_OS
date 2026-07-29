import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import ModuleRun from "@/pages/ModuleRun";
import RunDetail from "@/pages/RunDetail";
import RunHistory from "@/pages/RunHistory";
import Admin from "@/pages/Admin";

function ProtectedLayout() {
  const { isAuthenticated, isLoading } = useAuth();
  // No login screen by default (backend AUTH_REQUIRED=false resolves everyone
  // to a shared local user via GET /api/auth/me) - only redirect to /login if
  // that call actually failed, i.e. AUTH_REQUIRED was turned on server-side.
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/modules/:moduleKey" element={<ModuleRun />} />
        <Route path="/runs" element={<RunHistory />} />
        <Route path="/runs/:runId" element={<RunDetail />} />
        <Route path="/admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

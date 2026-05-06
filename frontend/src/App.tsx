import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './stores/authStore';
import Login from './pages/Login';
import Register from './pages/Register';

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<ProtectedRoute><div>Dashboard</div></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><div>Chat</div></ProtectedRoute>} />
          <Route path="/trends" element={<ProtectedRoute><div>Trends</div></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute><div>Profile</div></ProtectedRoute>} />
          <Route path="/tasks" element={<ProtectedRoute><div>Tasks</div></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><div>Settings</div></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

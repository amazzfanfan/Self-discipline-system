import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { motion } from 'framer-motion';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login(email, password);
      navigate('/');
    } catch {
      setError('邮箱或密码错误');
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="bg-slate-900 rounded-2xl p-8 w-full max-w-md border border-slate-800">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white">⚡ 系统</h1>
          <p className="text-slate-400 mt-2">登录以继续你的成长之旅</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input type="email" placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" required />
          <input type="password" placeholder="密码" value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" required />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
            登录
          </button>
        </form>
        <p className="text-center text-slate-400 mt-6 text-sm">
          没有账号？<Link to="/register" className="text-blue-400 hover:underline">注册</Link>
        </p>
      </motion.div>
    </div>
  );
}

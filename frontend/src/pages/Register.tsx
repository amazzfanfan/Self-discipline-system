import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { motion } from 'framer-motion';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [error, setError] = useState('');
  const register = useAuthStore((s) => s.register);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await register(email, password, nickname);
      navigate('/onboarding');
    } catch {
      setError('注册失败，邮箱可能已被使用');
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="bg-slate-900 rounded-2xl p-8 w-full max-w-md border border-slate-800">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white">⚡ 系统</h1>
          <p className="text-slate-400 mt-2">创建你的成长账号</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input type="text" placeholder="昵称" value={nickname} onChange={(e) => setNickname(e.target.value)}
            className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" required />
          <input type="email" placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" required />
          <input type="password" placeholder="密码（至少10位）" value={password} onChange={(e) => setPassword(e.target.value)}
            minLength={10} maxLength={128} className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" required />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button type="submit" className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
            注册
          </button>
        </form>
        <p className="text-center text-slate-400 mt-6 text-sm">
          已有账号？<Link to="/login" className="text-blue-400 hover:underline">登录</Link>
        </p>
      </motion.div>
    </div>
  );
}

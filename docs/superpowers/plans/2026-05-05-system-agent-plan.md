# System Agent 个人成长系统 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个AI驱动的个人外形提升系统，通过每日任务、累计评分、AI对话引导用户持续改善自己。

**Architecture:** 模块化单体架构。React SPA前端 + FastAPI异步后端 + PostgreSQL持久化 + Redis缓存。AI服务层封装通义千问/文心API。

**Tech Stack:** React 18, TypeScript, Vite, TailwindCSS, Zustand, React Query, Framer Motion, Recharts, Python, FastAPI, PostgreSQL, Redis, APScheduler

---

## 阶段一：项目脚手架与基础设施

### Task 1: 后端项目初始化

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/core/security.py`
- Create: `backend/.env.example`

- [ ] **Step 1: 创建后端目录结构和依赖文件**

```txt
# backend/requirements.txt
fastapi==0.111.0
uvicorn[standard]==0.30.1
sqlalchemy[asyncio]==2.0.31
asyncpg==0.29.0
alembic==1.13.1
redis[hiredis]==5.0.7
pydantic==2.7.4
pydantic-settings==2.3.4
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
httpx==0.27.0
apscheduler==3.10.4
slowapi==0.1.9
python-dotenv==1.0.1
```

- [ ] **Step 2: 创建配置模块**

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    APP_NAME: str = "System Agent"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    AI_MODEL: str = "qwen-vl-plus"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: 创建数据库连接模块**

```python
# backend/app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 4: 创建安全模块**

```python
# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
```

- [ ] **Step 5: 创建FastAPI主入口**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 创建环境变量模板**

```bash
# backend/.env.example
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-change-in-production
AI_API_KEY=your-ai-api-key
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen-vl-plus
```

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: initialize backend project with FastAPI scaffold"
```

---

### Task 2: 数据库模型与迁移

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/score.py`
- Create: `backend/app/models/task.py`
- Create: `backend/app/models/conversation.py`
- Create: `backend/app/models/weight.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`

- [ ] **Step 1: 创建用户模型**

```python
# backend/app/models/user.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum

class GenderEnum(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(100), nullable=False)
    avatar_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    scores = relationship("UserScore", back_populates="user")
    tasks = relationship("Task", back_populates="user")

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    height_cm = Column(Numeric(5, 1))
    weight_kg = Column(Numeric(5, 1))
    age = Column(Integer)
    gender = Column(SAEnum(GenderEnum))
    body_fat_pct = Column(Numeric(4, 1))
    front_photo_url = Column(String(500))
    side_photo_url = Column(String(500))
    ai_profile_score = Column(JSON)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profile")
```

- [ ] **Step 2: 创建评分模型**

```python
# backend/app/models/score.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.core.database import Base
import enum

class DimensionEnum(str, enum.Enum):
    exercise = "exercise"
    diet = "diet"
    sleep = "sleep"
    appearance = "appearance"

class UserScore(Base):
    __tablename__ = "user_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    score = Column(Numeric(4, 1), default=50.0)
    total_positive_count = Column(Integer, default=0)
    total_negative_count = Column(Integer, default=0)
    streak_days = Column(Integer, default=0)
    last_score_change = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="scores")

class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    delta = Column(Numeric(3, 1), nullable=False)
    reason = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 3: 创建任务模型**

```python
# backend/app/models/task.py
import uuid
from datetime import datetime, date, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum
from app.models.score import DimensionEnum

class TaskStatusEnum(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"

class DifficultyEnum(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    dimension = Column(SAEnum(DimensionEnum), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    difficulty = Column(SAEnum(DifficultyEnum), default=DifficultyEnum.medium)
    scheduled_date = Column(Date, nullable=False, index=True)
    status = Column(SAEnum(TaskStatusEnum), default=TaskStatusEnum.pending)
    completion_proof = Column(Text)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="tasks")
```

- [ ] **Step 4: 创建对话和体重模型**

```python
# backend/app/models/conversation.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum

class RoleEnum(str, enum.Enum):
    system = "system"
    user = "user"

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(SAEnum(RoleEnum), nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

```python
# backend/app/models/weight.py
import uuid
from datetime import datetime, date, timezone
from sqlalchemy import Column, DateTime, Date, ForeignKey, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class WeightRecord(Base):
    __tablename__ = "weight_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    weight_kg = Column(Numeric(5, 1), nullable=False)
    recorded_at = Column(Date, nullable=False)
    ai_evaluation = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 5: 初始化Alembic并生成迁移**

```bash
cd backend
alembic init alembic
# 修改 alembic.ini 中的 sqlalchemy.url
# 修改 alembic/env.py 导入 Base 和所有 models
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/ backend/alembic/
git commit -m "feat: add database models and Alembic migrations"
```

---

### Task 3: 前端项目初始化

**Files:**
- Create: `frontend/` (Vite project)
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/services/api.ts`
- Create: `frontend/src/stores/authStore.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/tailwind.config.js`

- [ ] **Step 1: 使用Vite创建React+TS项目**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite zustand @tanstack/react-query framer-motion recharts react-router-dom @headlessui/react axios
```

- [ ] **Step 2: 配置TailwindCSS**

```js
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

```css
/* frontend/src/index.css */
@import "tailwindcss";
```

- [ ] **Step 3: 创建TypeScript类型定义**

```typescript
// frontend/src/types/index.ts
export type Dimension = 'exercise' | 'diet' | 'sleep' | 'appearance';

export interface User {
  id: string;
  email: string;
  nickname: string;
  avatar_url: string | null;
}

export interface UserProfile {
  height_cm: number | null;
  weight_kg: number | null;
  age: number | null;
  gender: 'male' | 'female' | 'other' | null;
  body_fat_pct: number | null;
  front_photo_url: string | null;
  side_photo_url: string | null;
}

export interface UserScore {
  dimension: Dimension;
  score: number;
  streak_days: number;
}

export interface Task {
  id: string;
  dimension: Dimension;
  title: string;
  description: string;
  difficulty: 'easy' | 'medium' | 'hard';
  scheduled_date: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  completed_at: string | null;
}

export interface Conversation {
  id: string;
  role: 'system' | 'user';
  content: string;
  created_at: string;
}

export interface ScoreHistory {
  dimension: Dimension;
  delta: number;
  reason: string;
  created_at: string;
}
```

- [ ] **Step 4: 创建API客户端**

```typescript
// frontend/src/services/api.ts
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        const { data } = await axios.post('/api/auth/refresh', { refresh_token: refresh });
        localStorage.setItem('access_token', data.access_token);
        error.config.headers.Authorization = `Bearer ${data.access_token}`;
        return api(error.config);
      }
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

- [ ] **Step 5: 创建Zustand状态管理**

```typescript
// frontend/src/stores/authStore.ts
import { create } from 'zustand';
import api from '../services/api';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, nickname: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!localStorage.getItem('access_token'),

  login: async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    set({ isAuthenticated: true });
  },

  register: async (email, password, nickname) => {
    await api.post('/auth/register', { email, password, nickname });
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({ user: null, isAuthenticated: false });
  },

  fetchUser: async () => {
    const { data } = await api.get('/users/me');
    set({ user: data });
  },
}));
```

- [ ] **Step 6: 创建基础路由和App入口**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './stores/authStore';

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
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/register" element={<div>Register Page</div>} />
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
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: initialize React frontend with Vite, TailwindCSS, routing"
```

---

## 阶段二：认证模块

### Task 4: 后端认证API

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/modules/auth/__init__.py`
- Create: `backend/app/modules/auth/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建认证Schema**

```python
# backend/app/schemas/auth.py
from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: str
    password: str
    nickname: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str
```

- [ ] **Step 2: 创建认证路由**

```python
# backend/app/modules/auth/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.models.score import UserScore, DimensionEnum
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(email=req.email, password_hash=hash_password(req.password), nickname=req.nickname)
    db.add(user)
    await db.flush()

    # 初始化四维度评分，默认50分
    for dim in DimensionEnum:
        db.add(UserScore(user_id=user.id, dimension=dim, score=50.0))

    return {"message": "registered"}

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")

    return TokenResponse(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid refresh token")

    user_id = payload["sub"]
    return TokenResponse(
        access_token=create_access_token({"sub": user_id}),
        refresh_token=create_refresh_token({"sub": user_id}),
    )
```

- [ ] **Step 3: 注册路由到主应用**

```python
# backend/app/main.py (追加)
from app.modules.auth.router import router as auth_router
app.include_router(auth_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/ backend/app/modules/auth/
git commit -m "feat: add auth module with register, login, JWT refresh"
```

---

### Task 5: 前端认证页面

**Files:**
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/pages/Register.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 创建登录页面**

```tsx
// frontend/src/pages/Login.tsx
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
```

- [ ] **Step 2: 创建注册页面**

```tsx
// frontend/src/pages/Register.tsx
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
      navigate('/login');
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
          <input type="password" placeholder="密码（至少6位）" value={password} onChange={(e) => setPassword(e.target.value)}
            minLength={6} className="w-full px-4 py-3 bg-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" required />
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
```

- [ ] **Step 3: 更新App路由使用真实页面**

```tsx
// frontend/src/App.tsx — 替换路由中的占位div
import Login from './pages/Login';
import Register from './pages/Register';
// ...
<Route path="/login" element={<Login />} />
<Route path="/register" element={<Register />} />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ frontend/src/App.tsx
git commit -m "feat: add login and register pages with dark theme"
```

---

## 阶段三：用户模块

### Task 6: 用户API与画像管理

**Files:**
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/modules/user/router.py`
- Create: `backend/app/core/deps.py`

- [ ] **Step 1: 创建认证依赖**

```python
# backend/app/core/deps.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(401, "Invalid token")
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "User not found")
    return user
```

- [ ] **Step 2: 创建用户Schema和路由**

```python
# backend/app/schemas/user.py
from pydantic import BaseModel
from uuid import UUID

class UserResponse(BaseModel):
    id: UUID
    email: str
    nickname: str
    avatar_url: str | None

    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    age: int | None = None
    gender: str | None = None

class ProfileResponse(BaseModel):
    height_cm: float | None
    weight_kg: float | None
    age: int | None
    gender: str | None
    front_photo_url: str | None
    side_photo_url: str | None

    class Config:
        from_attributes = True
```

```python
# backend/app/modules/user/router.py
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserProfile
from app.schemas.user import UserResponse, ProfileUpdate, ProfileResponse

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user

@router.get("/me/profile", response_model=ProfileResponse)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
        return profile
    return user.profile

@router.put("/me/profile", response_model=ProfileResponse)
async def update_profile(req: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = user.profile
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    return profile

@router.post("/me/photos")
async def upload_photo(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    # TODO: 上传到OSS，返回URL
    # 临时方案：保存到本地
    import os
    os.makedirs("uploads", exist_ok=True)
    path = f"uploads/{user.id}_{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"url": f"/uploads/{user.id}_{file.filename}"}
```

- [ ] **Step 3: 注册路由**

```python
# backend/app/main.py (追加)
from app.modules.user.router import router as user_router
app.include_router(user_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/user/ backend/app/schemas/user.py backend/app/core/deps.py
git commit -m "feat: add user module with profile CRUD and photo upload"
```

---

## 阶段四：评分模块

### Task 7: 评分API与算法

**Files:**
- Create: `backend/app/schemas/score.py`
- Create: `backend/app/modules/score/router.py`
- Create: `backend/app/services/score_service.py`

- [ ] **Step 1: 创建评分服务**

```python
# backend/app/services/score_service.py
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.score import UserScore, ScoreHistory, DimensionEnum

THRESHOLDS = {
    DimensionEnum.exercise: 7,
    DimensionEnum.diet: 5,
    DimensionEnum.sleep: 7,
    DimensionEnum.appearance: 14,
}

async def record_task_completion(db: AsyncSession, user_id: str, dimension: DimensionEnum) -> dict | None:
    """记录任务完成，检查是否达到加分阈值。返回分数变动信息或None。"""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    score_record.streak_days += 1
    score_record.total_positive_count += 1

    threshold = THRESHOLDS[dimension]
    if score_record.streak_days >= threshold and score_record.streak_days % threshold == 0:
        score_record.score = min(100, float(score_record.score) + 0.1)
        score_record.last_score_change = datetime.now(timezone.utc)

        history = ScoreHistory(
            user_id=user_id,
            dimension=dimension,
            delta=0.1,
            reason=f"连续{score_record.streak_days}天完成{dimension.value}任务",
        )
        db.add(history)
        return {"dimension": dimension, "delta": 0.1, "streak": score_record.streak_days}

    return None

async def record_negative(db: AsyncSession, user_id: str, dimension: DimensionEnum, reason: str) -> dict:
    """记录负向行为，扣分。"""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    score_record.score = max(0, float(score_record.score) - 0.1)
    score_record.streak_days = 0
    score_record.total_negative_count += 1
    score_record.last_score_change = datetime.now(timezone.utc)

    history = ScoreHistory(
        user_id=user_id,
        dimension=dimension,
        delta=-0.1,
        reason=reason,
    )
    db.add(history)
    return {"dimension": dimension, "delta": -0.1}

async def get_streak_info(db: AsyncSession, user_id: str) -> list[dict]:
    """获取所有维度的连续天数和进度信息。"""
    result = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    scores = result.scalars().all()

    return [
        {
            "dimension": s.dimension,
            "score": float(s.score),
            "streak_days": s.streak_days,
            "threshold": THRESHOLDS[s.dimension],
            "progress": min(1.0, s.streak_days / THRESHOLDS[s.dimension]),
        }
        for s in scores
    ]
```

- [ ] **Step 2: 创建评分路由**

```python
# backend/app/modules/score/router.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.score import UserScore, ScoreHistory

router = APIRouter(prefix="/api/scores", tags=["scores"])

@router.get("")
async def get_scores(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
    scores = result.scalars().all()
    return [
        {"dimension": s.dimension.value, "score": float(s.score), "streak_days": s.streak_days}
        for s in scores
    ]

@router.get("/history")
async def get_score_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 50):
    result = await db.execute(
        select(ScoreHistory).where(ScoreHistory.user_id == user.id).order_by(ScoreHistory.created_at.desc()).limit(limit)
    )
    return [
        {"dimension": h.dimension.value, "delta": float(h.delta), "reason": h.reason, "created_at": h.created_at.isoformat()}
        for h in result.scalars().all()
    ]

@router.get("/trends")
async def get_trends(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScoreHistory).where(ScoreHistory.user_id == user.id).order_by(ScoreHistory.created_at)
    )
    history = result.scalars().all()

    trends = {}
    for h in history:
        dim = h.dimension.value
        if dim not in trends:
            trends[dim] = []
        trends[dim].append({"delta": float(h.delta), "date": h.created_at.isoformat()})

    return trends
```

- [ ] **Step 3: 注册路由**

```python
# backend/app/main.py (追加)
from app.modules.score.router import router as score_router
app.include_router(score_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/score/ backend/app/services/score_service.py backend/app/schemas/score.py
git commit -m "feat: add score module with streak algorithm and history"
```

---

## 阶段五：任务模块

### Task 8: 任务API

**Files:**
- Create: `backend/app/modules/task/router.py`
- Modify: `backend/app/services/score_service.py`

- [ ] **Step 1: 创建任务路由**

```python
# backend/app/modules/task/router.py
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatusEnum
from app.models.score import DimensionEnum
from app.services.score_service import record_task_completion

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

@router.get("/today")
async def get_today_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(and_(Task.user_id == user.id, Task.scheduled_date == date.today()))
    )
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id), "dimension": t.dimension.value, "title": t.title,
            "description": t.description, "difficulty": t.difficulty.value,
            "status": t.status.value, "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]

@router.post("/{task_id}/complete")
async def complete_task(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status == TaskStatusEnum.completed:
        raise HTTPException(400, "Already completed")

    from datetime import datetime, timezone
    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)

    score_change = await record_task_completion(db, user.id, task.dimension)

    return {
        "message": "任务完成",
        "score_change": score_change,
    }

@router.get("")
async def list_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                     dimension: str | None = None, status: str | None = None, limit: int = 20):
    query = select(Task).where(Task.user_id == user.id)
    if dimension:
        query = query.where(Task.dimension == dimension)
    if status:
        query = query.where(Task.status == status)
    query = query.order_by(Task.scheduled_date.desc()).limit(limit)

    result = await db.execute(query)
    return [
        {
            "id": str(t.id), "dimension": t.dimension.value, "title": t.title,
            "scheduled_date": t.scheduled_date.isoformat(), "status": t.status.value,
        }
        for t in result.scalars().all()
    ]
```

- [ ] **Step 2: 注册路由**

```python
# backend/app/main.py (追加)
from app.modules.task.router import router as task_router
app.include_router(task_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/task/
git commit -m "feat: add task module with today tasks and completion flow"
```

---

## 阶段六：AI服务层

### Task 9: AI服务集成

**Files:**
- Create: `backend/app/services/ai_service.py`

- [ ] **Step 1: 创建AI服务**

```python
# backend/app/services/ai_service.py
import httpx
from app.core.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = """你是一个名为"系统"的AI助手，灵感来源于小说中的成长系统。你的职责是帮助用户提升自己。
你不是朋友，不是医生，而是一个严格但关怀的引导者。你用数据说话，用鼓励驱动，偶尔带一点幽默。
你相信持续的小进步会带来大变化。

对话原则：
- 不批评，不说教，用数据和事实引导
- 承认人性，偶尔放松是正常的
- 关注趋势，单次失败不代表失败
- 主动关怀，检测到异常时主动询问
- 保持人设，始终以"系统"身份对话"""

async def chat_completion(messages: list[dict], user_context: str = "") -> str:
    """调用AI模型生成对话回复。"""
    system_msg = SYSTEM_PROMPT
    if user_context:
        system_msg += f"\n\n用户上下文：{user_context}"

    full_messages = [{"role": "system", "content": system_msg}] + messages

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.AI_MODEL, "messages": full_messages, "max_tokens": 500},
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]

async def generate_task(nickname: str, dimension: str, score: float, difficulty: str, recent_tasks: list[str]) -> str:
    """AI生成每日任务。"""
    recent = "、".join(recent_tasks[-5:]) if recent_tasks else "无"
    prompt = f"用户{nickname}，{dimension}维度当前评分{score}分。请生成1个今日任务，难度{difficulty}，具体可执行，有明确完成标准。最近做过的任务：{recent}，请避免重复。只返回任务标题，不要其他内容。"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.AI_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 100},
        )
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

async def evaluate_initial_score(height_cm: float, weight_kg: float, age: int, gender: str) -> dict:
    """AI评估初始评分。"""
    prompt = f"""基于以下用户数据评估四个维度的得分（0-100）：
身高：{height_cm}cm，体重：{weight_kg}kg，年龄：{age}岁，性别：{gender}

请以JSON格式返回，包含四个维度：
- exercise: 运动/体态评分
- diet: 饮食/营养评分
- sleep: 睡眠/作息评分
- appearance: 外貌/皮肤评分

参考中国成年人健康标准，BMI正常范围18.5-24。只返回JSON，不要其他内容。"""

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.AI_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 200},
        )
        data = response.json()
        import json
        return json.loads(data["choices"][0]["message"]["content"])

async def analyze_image(image_url: str, analysis_type: str) -> str:
    """AI分析用户上传的图片。"""
    prompt_map = {
        "body": "请分析这张身材照片，评估体态、肌肉线条、整体外形。给出0-100的评分和简要分析。",
        "face": "请分析这张面部照片，评估皮肤状态、精神面貌。给出0-100的评分和简要分析。",
    }
    prompt = prompt_map.get(analysis_type, "请分析这张图片。")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": settings.AI_MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]}],
                "max_tokens": 300,
            },
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: add AI service layer with chat, task generation, image analysis"
```

---

## 阶段七：对话模块

### Task 10: 对话API与WebSocket

**Files:**
- Create: `backend/app/modules/chat/router.py`

- [ ] **Step 1: 创建对话路由**

```python
# backend/app/modules/chat/router.py
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db, async_session
from app.core.deps import get_current_user
from app.models.user import User
from app.models.conversation import Conversation, RoleEnum
from app.services.ai_service import chat_completion

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("/send")
async def send_message(content: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # 保存用户消息
    user_msg = Conversation(user_id=user.id, role=RoleEnum.user, content=content)
    db.add(user_msg)

    # 获取历史上下文（最近10条）
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc()).limit(10)
    )
    history = list(reversed(result.scalars().all()))
    messages = [{"role": h.role.value, "content": h.content} for h in history]
    messages.append({"role": "user", "content": content})

    # 构建用户上下文
    user_context = f"用户昵称：{user.nickname}"

    # AI回复
    ai_reply = await chat_completion(messages, user_context)

    # 保存AI回复
    sys_msg = Conversation(user_id=user.id, role=RoleEnum.system, content=ai_reply)
    db.add(sys_msg)

    return {"reply": ai_reply}

@router.get("/history")
async def get_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 50):
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc()).limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        {"id": str(m.id), "role": m.role.value, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in messages
    ]
```

- [ ] **Step 2: 注册路由**

```python
# backend/app/main.py (追加)
from app.modules.chat.router import router as chat_router
app.include_router(chat_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/chat/
git commit -m "feat: add chat module with message send and history"
```

---

## 阶段八：体重模块

### Task 11: 体重记录API

**Files:**
- Create: `backend/app/modules/weight/router.py`

- [ ] **Step 1: 创建体重路由**

```python
# backend/app/modules/weight/router.py
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.weight import WeightRecord

router = APIRouter(prefix="/api/weight", tags=["weight"])

class WeightRequest(BaseModel):
    weight_kg: float

@router.post("")
async def record_weight(req: WeightRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    record = WeightRecord(user_id=user.id, weight_kg=req.weight_kg, recorded_at=date.today())
    db.add(record)
    return {"message": "体重已记录", "weight_kg": req.weight_kg}

@router.get("/history")
async def get_weight_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 30):
    result = await db.execute(
        select(WeightRecord).where(WeightRecord.user_id == user.id)
        .order_by(WeightRecord.recorded_at.desc()).limit(limit)
    )
    return [
        {"weight_kg": float(w.weight_kg), "recorded_at": w.recorded_at.isoformat()}
        for w in result.scalars().all()
    ]
```

- [ ] **Step 2: 注册路由**

```python
# backend/app/main.py (追加)
from app.modules.weight.router import router as weight_router
app.include_router(weight_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/weight/
git commit -m "feat: add weight module with recording and history"
```

---

## 阶段九：定时任务调度

### Task 12: APScheduler定时任务

**Files:**
- Create: `backend/app/services/scheduler_service.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建调度服务**

```python
# backend/app/services/scheduler_service.py
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from app.core.database import async_session
from app.models.user import User
from app.models.score import UserScore, DimensionEnum
from app.models.task import Task, DifficultyEnum
from app.services.ai_service import generate_task

scheduler = AsyncIOScheduler()

TASKS_PER_DIMENSION = {
    DimensionEnum.exercise: 1,
    DimensionEnum.diet: 1,
    DimensionEnum.sleep: 1,
    DimensionEnum.appearance: 1,
}

async def daily_task_generation():
    """每日8:00为所有用户生成任务。"""
    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            # 获取用户各维度评分
            scores_result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
            scores = {s.dimension: s for s in scores_result.scalars().all()}

            for dim, count in TASKS_PER_DIMENSION.items():
                score_record = scores.get(dim)
                if not score_record:
                    continue

                # 根据评分决定难度
                score_val = float(score_record.score)
                if score_val < 50:
                    difficulty = DifficultyEnum.easy
                elif score_val < 70:
                    difficulty = DifficultyEnum.medium
                else:
                    difficulty = DifficultyEnum.hard

                # AI生成任务
                try:
                    task_title = await generate_task(
                        nickname=user.nickname,
                        dimension=dim.value,
                        score=score_val,
                        difficulty=difficulty.value,
                        recent_tasks=[],
                    )
                except Exception:
                    # AI失败时使用默认任务
                    defaults = {
                        DimensionEnum.exercise: "运动30分钟",
                        DimensionEnum.diet: "健康饮食一天",
                        DimensionEnum.sleep: "23:00前入睡",
                        DimensionEnum.appearance: "认真护肤一次",
                    }
                    task_title = defaults[dim]

                task = Task(
                    user_id=user.id,
                    dimension=dim,
                    title=task_title,
                    description="",
                    difficulty=difficulty,
                    scheduled_date=date.today(),
                )
                db.add(task)

        await db.commit()

def start_scheduler():
    scheduler.add_job(daily_task_generation, "cron", hour=8, minute=0, id="daily_tasks")
    scheduler.start()
```

- [ ] **Step 2: 在主应用中启动调度器**

```python
# backend/app/main.py (追加)
from app.services.scheduler_service import start_scheduler

@app.on_event("startup")
async def startup():
    start_scheduler()
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scheduler_service.py backend/app/main.py
git commit -m "feat: add APScheduler for daily task generation"
```

---

## 阶段十：前端核心页面

### Task 13: Dashboard页面

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/components/ScoreRing.tsx`
- Create: `frontend/src/components/DimensionBar.tsx`

- [ ] **Step 1: 创建评分环形组件**

```tsx
// frontend/src/components/ScoreRing.tsx
import { motion } from 'framer-motion';

interface Props {
  score: number;
  label?: string;
}

export default function ScoreRing({ score, label = '综合评分' }: Props) {
  const circumference = 2 * Math.PI * 45;
  const progress = (score / 100) * circumference;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="120" height="120" className="-rotate-90">
        <circle cx="60" cy="60" r="45" stroke="#1e293b" strokeWidth="8" fill="none" />
        <motion.circle
          cx="60" cy="60" r="45" stroke="url(#gradient)" strokeWidth="8" fill="none"
          strokeLinecap="round" strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - progress }}
          transition={{ duration: 1.5, ease: "easeOut" }}
        />
        <defs>
          <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-bold text-white">{score.toFixed(1)}</div>
        <div className="text-xs text-slate-400">{label}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建维度进度条组件**

```tsx
// frontend/src/components/DimensionBar.tsx
import { motion } from 'framer-motion';

const COLORS = {
  exercise: { bar: 'from-blue-500 to-blue-400', text: 'text-blue-400', icon: '🏃' },
  diet: { bar: 'from-emerald-500 to-emerald-400', text: 'text-emerald-400', icon: '🥗' },
  sleep: { bar: 'from-violet-500 to-violet-400', text: 'text-violet-400', icon: '😴' },
  appearance: { bar: 'from-pink-500 to-pink-400', text: 'text-pink-400', icon: '✨' },
};

interface Props {
  dimension: string;
  score: number;
  streak: number;
  threshold: number;
}

export default function DimensionBar({ dimension, score, streak, threshold }: Props) {
  const colors = COLORS[dimension as keyof typeof COLORS] || COLORS.exercise;
  const progress = Math.min(100, (streak / threshold) * 100);

  return (
    <div className="mb-4">
      <div className="flex justify-between items-center mb-1">
        <span className={`${colors.text} text-sm`}>{colors.icon} {dimension}</span>
        <span className="text-slate-300 text-sm">{score.toFixed(1)}</span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <motion.div
          className={`h-full bg-gradient-to-r ${colors.bar} rounded-full`}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </div>
      <div className="text-xs text-slate-500 mt-1">连续 {streak}/{threshold} 天</div>
    </div>
  );
}
```

- [ ] **Step 3: 创建Dashboard页面**

```tsx
// frontend/src/pages/Dashboard.tsx
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import api from '../services/api';
import ScoreRing from '../components/ScoreRing';
import DimensionBar from '../components/DimensionBar';

export default function Dashboard() {
  const { data: scores } = useQuery({
    queryKey: ['scores'],
    queryFn: () => api.get('/scores').then((r) => r.data),
  });

  const { data: tasks } = useQuery({
    queryKey: ['today-tasks'],
    queryFn: () => api.get('/tasks/today').then((r) => r.data),
  });

  const avgScore = scores ? scores.reduce((a: number, s: any) => a + s.score, 0) / scores.length : 0;

  return (
    <div className="min-h-screen bg-slate-950 p-6">
      <div className="max-w-2xl mx-auto">
        <motion.h1 initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="text-2xl font-bold text-white mb-6">⚡ 系统</motion.h1>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-6 flex items-center gap-8">
          <ScoreRing score={avgScore} />
          <div className="flex-1">
            {scores?.map((s: any) => (
              <DimensionBar key={s.dimension} dimension={s.dimension}
                score={s.score} streak={s.streak_days} threshold={7} />
            ))}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
          <h2 className="text-lg text-slate-300 mb-4">今日任务</h2>
          {tasks?.length === 0 && <p className="text-slate-500">暂无任务，等待系统发布...</p>}
          {tasks?.map((t: any) => (
            <div key={t.id} className="bg-slate-800 rounded-lg p-3 mb-2 flex justify-between items-center">
              <div>
                <div className="text-white text-sm">{t.title}</div>
                <div className="text-slate-500 text-xs">{t.difficulty}</div>
              </div>
              <span className={`text-xs px-2 py-1 rounded ${
                t.status === 'completed' ? 'bg-emerald-900 text-emerald-400' : 'bg-slate-700 text-slate-400'
              }`}>
                {t.status === 'completed' ? '已完成' : '待完成'}
              </span>
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 更新App路由**

```tsx
// frontend/src/App.tsx — 添加Dashboard导入和路由
import Dashboard from './pages/Dashboard';
// <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/components/
git commit -m "feat: add Dashboard page with score ring and dimension bars"
```

---

### Task 14: 对话页面

**Files:**
- Create: `frontend/src/pages/Chat.tsx`

- [ ] **Step 1: 创建对话页面**

```tsx
// frontend/src/pages/Chat.tsx
import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';

interface Message {
  id: string;
  role: 'system' | 'user';
  content: string;
  created_at: string;
}

export default function Chat() {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: history } = useQuery({
    queryKey: ['chat-history'],
    queryFn: () => api.get('/chat/history').then((r) => r.data),
  });

  const sendMutation = useMutation({
    mutationFn: (content: string) => api.post('/chat/send', null, { params: { content } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-history'] });
    },
  });

  const messages: Message[] = history || [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMutation.mutate(input);
    setInput('');
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <div className="bg-slate-900 border-b border-slate-800 p-4">
        <h1 className="text-lg font-bold text-white">⚡ 系统对话</h1>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 max-w-2xl mx-auto w-full">
        <AnimatePresence>
          {messages.map((msg) => (
            <motion.div key={msg.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role === 'system' && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center text-sm flex-shrink-0">
                  ⚡
                </div>
              )}
              <div className={`max-w-[75%] rounded-2xl px-4 py-2 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-slate-800 text-slate-200 rounded-bl-sm'
              }`}>
                <div className="text-xs text-slate-400 mb-1">
                  {msg.role === 'system' ? '系统' : '你'} · {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                </div>
                <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="bg-slate-900 border-t border-slate-800 p-4">
        <div className="max-w-2xl mx-auto flex gap-3">
          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="输入消息..."
            className="flex-1 px-4 py-3 bg-slate-800 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button onClick={handleSend} disabled={sendMutation.isPending}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white rounded-xl font-medium transition-colors">
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Chat.tsx
git commit -m "feat: add Chat page with real-time messaging UI"
```

---

### Task 15: 趋势页面

**Files:**
- Create: `frontend/src/pages/Trends.tsx`

- [ ] **Step 1: 创建趋势页面**

```tsx
// frontend/src/pages/Trends.tsx
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { motion } from 'framer-motion';
import api from '../services/api';

const DIM_COLORS = {
  exercise: '#3b82f6',
  diet: '#10b981',
  sleep: '#8b5cf6',
  appearance: '#ec4899',
};

export default function Trends() {
  const { data: scores } = useQuery({
    queryKey: ['scores'],
    queryFn: () => api.get('/scores').then((r) => r.data),
  });

  const { data: history } = useQuery({
    queryKey: ['score-history'],
    queryFn: () => api.get('/scores/history?limit=100').then((r) => r.data),
  });

  // 构建图表数据
  const chartData = (history || []).reverse().map((h: any, i: number) => ({
    index: i + 1,
    [h.dimension]: Math.abs(h.delta),
    date: new Date(h.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
  }));

  return (
    <div className="min-h-screen bg-slate-950 p-6">
      <div className="max-w-4xl mx-auto">
        <motion.h1 initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="text-2xl font-bold text-white mb-6">评分趋势</motion.h1>

        {/* 当前评分卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {scores?.map((s: any) => (
            <motion.div key={s.dimension} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
              className="bg-slate-900 rounded-xl p-4 border border-slate-800 text-center">
              <div className="text-2xl font-bold" style={{ color: DIM_COLORS[s.dimension as keyof typeof DIM_COLORS] }}>
                {s.score.toFixed(1)}
              </div>
              <div className="text-sm text-slate-400 mt-1">{s.dimension}</div>
              <div className="text-xs text-slate-500 mt-1">连续 {s.streak_days} 天</div>
            </motion.div>
          ))}
        </div>

        {/* 趋势图表 */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
          <h2 className="text-lg text-slate-300 mb-4">评分变动历史</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
              <Legend />
              {Object.entries(DIM_COLORS).map(([dim, color]) => (
                <Line key={dim} type="monotone" dataKey={dim} stroke={color} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </motion.div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Trends.tsx
git commit -m "feat: add Trends page with score history charts"
```

---

## 阶段十一：安全与优化

### Task 16: 安全加固

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 添加限流和安全中间件**

```python
# backend/app/main.py (追加)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 对认证接口添加限流
# 在路由函数上使用 @limiter.limit("5/minute") 装饰器
```

- [ ] **Step 2: 添加Redis缓存层**

```python
# backend/app/services/cache_service.py
import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()
redis_client = redis.from_url(settings.REDIS_URL)

async def get_cached(key: str) -> str | None:
    return await redis_client.get(key)

async def set_cached(key: str, value: str, ttl: int = 300):
    await redis_client.setex(key, ttl, value)

async def delete_cached(key: str):
    await redis_client.delete(key)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py backend/app/services/cache_service.py
git commit -m "feat: add rate limiting and Redis caching layer"
```

---

### Task 17: 结构化日志

**Files:**
- Create: `backend/app/core/logging.py`

- [ ] **Step 1: 创建日志配置**

```python
# backend/app/core/logging.py
import logging
import json
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/logging.py
git commit -m "feat: add structured JSON logging"
```

---

## 阶段十二：部署配置

### Task 18: Docker与部署

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: 后端Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: docker-compose.yml**

```yaml
# docker-compose.yml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: ./backend/.env
    depends_on:
      - postgres
      - redis

  frontend:
    build: ./frontend
    ports:
      - "3000:80"

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: system_agent
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml backend/Dockerfile frontend/Dockerfile
git commit -m "feat: add Docker and docker-compose deployment config"
```

---

## 实现顺序总结

| 阶段 | 任务 | 交付物 |
|------|------|--------|
| 1 | Task 1-3 | 项目脚手架，前后端可启动 |
| 2 | Task 4-5 | 注册/登录功能可用 |
| 3 | Task 6 | 用户画像CRUD |
| 4 | Task 7 | 评分算法运行 |
| 5 | Task 8 | 任务完成流程 |
| 6 | Task 9 | AI服务集成 |
| 7 | Task 10 | 对话功能可用 |
| 8 | Task 11 | 体重记录 |
| 9 | Task 12 | 定时任务自动生成 |
| 10 | Task 13-15 | 前端核心页面完成 |
| 11 | Task 16-17 | 安全加固+日志 |
| 12 | Task 18 | 部署配置 |

每个阶段完成后都可以运行和测试，逐步迭代直到完整交付。

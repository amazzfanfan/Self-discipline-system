-- 本地 PostgreSQL 只需要安装并启用 pgvector 扩展。
-- 表结构和索引统一交给 Alembic 管理，避免脚本与迁移产生冲突。
CREATE EXTENSION IF NOT EXISTS vector;

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';

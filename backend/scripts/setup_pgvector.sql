-- pgvector 扩展设置脚本
-- 在 PostgreSQL 数据库中运行此脚本以启用向量数据库支持

-- 1. 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 验证安装
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE NOTICE 'pgvector 扩展已成功安装';
    ELSE
        RAISE EXCEPTION 'pgvector 扩展安装失败';
    END IF;
END $$;

-- 3. 创建向量索引优化配置
-- 注意：这些配置在创建表后执行

-- 示例：创建 memories 表（如果不存在）
-- 这个表将用于存储对话的向量嵌入
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    role VARCHAR(20) NOT NULL,
    embedding vector(1536),  -- OpenAI ada-002 维度
    memory_type VARCHAR(50) DEFAULT 'conversation',
    importance_score FLOAT DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. 创建索引
-- 向量相似度索引（IVFFlat）
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
ON memories USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 用户 ID 索引
CREATE INDEX IF NOT EXISTS idx_memories_user_id 
ON memories(user_id);

-- 记忆类型索引
CREATE INDEX IF NOT EXISTS idx_memories_type 
ON memories(memory_type);

-- 创建时间索引
CREATE INDEX IF NOT EXISTS idx_memories_created_at 
ON memories(created_at DESC);

-- 5. 创建自动更新时间戳的触发器
CREATE OR REPLACE FUNCTION update_memory_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_accessed = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_memory_timestamp
BEFORE UPDATE ON memories
FOR EACH ROW
EXECUTE FUNCTION update_memory_timestamp();

-- 6. 添加注释
COMMENT ON TABLE memories IS '存储对话记忆和向量嵌入的表';
COMMENT ON COLUMN memories.embedding IS '文本的向量表示，用于语义相似度搜索';
COMMENT ON COLUMN memories.importance_score IS '记忆的重要性评分，0-1之间';
COMMENT ON COLUMN memories.memory_type IS '记忆类型：conversation(对话), preference(偏好), fact(事实)';

-- 完成
DO $$
BEGIN
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'pgvector 设置完成！';
    RAISE NOTICE '==========================================';
    RAISE NOTICE '已创建：';
    RAISE NOTICE '  - memories 表';
    RAISE NOTICE '  - 向量索引 (IVFFlat)';
    RAISE NOTICE '  - 辅助索引';
    RAISE NOTICE '  - 自动更新触发器';
    RAISE NOTICE '==========================================';
END $$;

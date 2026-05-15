"""
Embedding Service - 向量嵌入服务
使用阿里云 DashScope Embedding API 生成文本向量
"""

import httpx
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# DashScope Embedding API 端点
EMBEDDING_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"


class EmbeddingService:
    """
    向量嵌入服务类
    使用阿里云 DashScope Embedding API 生成文本向量
    """
    
    def __init__(self):
        self.api_key = settings.EMBEDDING_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
    
    async def get_embedding(self, text: str) -> list[float]:
        """
        获取单个文本的向量嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            向量嵌入列表，长度为 dimension (1536)
        """
        try:
            logger.info(f"Getting embedding for text: {len(text)} chars")
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    EMBEDDING_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "input": {
                            "texts": [text]
                        }
                    },
                )
                
                if response.status_code != 200:
                    logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                    raise Exception(f"Embedding API returned status {response.status_code}")
                
                data = response.json()
                
                # 从响应中提取嵌入向量
                embeddings = data.get("output", {}).get("embeddings", [])
                if not embeddings:
                    raise Exception("No embeddings returned from API")
                
                embedding = embeddings[0].get("embedding", [])
                if not embedding:
                    raise Exception("Empty embedding returned")
                
                logger.info(f"Embedding received: dimension={len(embedding)}")
                return embedding
                
        except httpx.TimeoutException:
            logger.error("Embedding API timeout")
            raise Exception("Embedding API timeout")
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise
    
    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量获取文本的向量嵌入
        
        Args:
            texts: 文本列表
            
        Returns:
            向量嵌入列表，每个元素是一个向量
        """
        if not texts:
            return []
        
        try:
            logger.info(f"Batch embedding: {len(texts)} texts")
            
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    EMBEDDING_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "input": {
                            "texts": texts
                        }
                    },
                )
                
                if response.status_code != 200:
                    logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                    raise Exception(f"Embedding API returned status {response.status_code}")
                
                data = response.json()
                
                # 从响应中提取嵌入向量
                embeddings_data = data.get("output", {}).get("embeddings", [])
                if not embeddings_data:
                    raise Exception("No embeddings returned from API")
                
                # 按 text_index 排序，确保顺序正确
                embeddings_data.sort(key=lambda x: x.get("text_index", 0))
                
                result = []
                for item in embeddings_data:
                    embedding = item.get("embedding", [])
                    if not embedding:
                        raise Exception(f"Empty embedding for text_index {item.get('text_index')}")
                    result.append(embedding)
                
                logger.info(f"Batch embedding completed: {len(result)} vectors")
                return result
                
        except httpx.TimeoutException:
            logger.error("Batch embedding API timeout")
            raise Exception("Embedding API timeout")
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise


# 全局实例，供其他模块导入使用
embedding_service = EmbeddingService()

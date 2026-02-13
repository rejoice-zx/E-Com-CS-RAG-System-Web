# -*- coding: utf-8 -*-
"""
知识库服务模块 - Knowledge Service

功能:
- 知识库CRUD操作
- 文本分块（Chunking）+ 向量索引同步
- 重复检测
- 导入导出
"""

import uuid
import logging
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem
from app.services.vector_service import VectorService
from app.core.config import Config
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def generate_knowledge_id() -> str:
    """生成唯一知识条目ID"""
    return f"kb_{uuid.uuid4().hex[:12]}"


# ==================== 分块工具函数 ====================

CHUNK_ID_SEP = "#chunk_"


def make_chunk_id(knowledge_id: str, chunk_index: int) -> str:
    """生成 chunk 级向量 ID，如 kb_xxxx#chunk_0"""
    return f"{knowledge_id}{CHUNK_ID_SEP}{chunk_index}"


def split_chunk_id(chunk_id: str) -> Tuple[str, int]:
    """将 chunk ID 解析回 (knowledge_id, chunk_index)，
    如果不含分隔符则视为整条知识（chunk_index = -1）。
    """
    if CHUNK_ID_SEP in chunk_id:
        parts = chunk_id.rsplit(CHUNK_ID_SEP, 1)
        try:
            return parts[0], int(parts[1])
        except (ValueError, IndexError):
            return chunk_id, -1
    return chunk_id, -1


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """按字符长度切片 + overlap 进行文本分块。

    Args:
        text: 待分块文本
        chunk_size: 每块最大字符数
        chunk_overlap: 相邻块重叠字符数

    Returns:
        分块列表（至少返回一个块）
    """
    if not text:
        return [""]
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return chunks


class KnowledgeService:
    """知识库服务类"""

    def __init__(self):
        self.vector_service = VectorService()
        self._config = Config()

    # ==================== 分块配置 ====================

    def _get_chunk_config(self) -> Tuple[int, int, int]:
        """返回 (chunk_size, chunk_overlap, chunk_max_per_item)"""
        cfg = self._config
        return (
            int(cfg.get("chunk_size", 500)),
            int(cfg.get("chunk_overlap", 50)),
            int(cfg.get("chunk_max_per_item", 10)),
        )

    # ==================== CRUD ====================

    async def create_knowledge(
        self,
        db: AsyncSession,
        question: str,
        answer: str,
        keywords: Optional[List[str]] = None,
        category: str = "通用",
        score: float = 1.0,
        sync_vector: bool = True,
        knowledge_id: Optional[str] = None,
    ) -> KnowledgeItem:
        knowledge_id = knowledge_id or generate_knowledge_id()

        # 如果指定了 ID 且已存在，先删除旧条目（用于商品知识同步的幂等写入）
        if knowledge_id:
            existing = await self.get_knowledge(db, knowledge_id)
            if existing:
                await self.delete_knowledge(db, knowledge_id, sync_vector=sync_vector)

        item = KnowledgeItem(
            id=knowledge_id,
            question=question,
            answer=answer,
            keywords=keywords or [],
            category=category,
            score=score,
            created_at=utcnow(),
            updated_at=utcnow()
        )

        db.add(item)
        await db.commit()
        await db.refresh(item)

        if sync_vector:
            await self._sync_vector_add(item, db=db)

        logger.info(f"创建知识条目: {knowledge_id}")
        return item

    async def get_knowledge(
        self,
        db: AsyncSession,
        knowledge_id: str
    ) -> Optional[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.id == knowledge_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_knowledge_list(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> Tuple[List[KnowledgeItem], int]:
        stmt = select(KnowledgeItem)
        count_stmt = select(func.count(KnowledgeItem.id))

        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
            count_stmt = count_stmt.where(KnowledgeItem.category == category)

        if keyword:
            search_pattern = f"%{keyword}%"
            keyword_filter = or_(
                KnowledgeItem.question.ilike(search_pattern),
                KnowledgeItem.answer.ilike(search_pattern)
            )
            stmt = stmt.where(keyword_filter)
            count_stmt = count_stmt.where(keyword_filter)

        stmt = stmt.order_by(KnowledgeItem.updated_at.desc())
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await db.execute(stmt)
        items = list(result.scalars().all())

        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        return items, total

    async def update_knowledge(
        self,
        db: AsyncSession,
        knowledge_id: str,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        category: Optional[str] = None,
        score: Optional[float] = None,
        sync_vector: bool = True
    ) -> Optional[KnowledgeItem]:
        item = await self.get_knowledge(db, knowledge_id)
        if not item:
            return None

        need_vector_update = False

        if question is not None:
            item.question = question
            need_vector_update = True
        if answer is not None:
            item.answer = answer
            need_vector_update = True
        if keywords is not None:
            item.keywords = keywords
        if category is not None:
            item.category = category
        if score is not None:
            item.score = score

        item.updated_at = utcnow()

        await db.commit()
        await db.refresh(item)

        if sync_vector and need_vector_update:
            await self._sync_vector_update(item, db=db)

        logger.info(f"更新知识条目: {knowledge_id}")
        return item

    async def delete_knowledge(
        self,
        db: AsyncSession,
        knowledge_id: str,
        sync_vector: bool = True
    ) -> bool:
        item = await self.get_knowledge(db, knowledge_id)
        if not item:
            return False

        await db.delete(item)
        await db.commit()

        if sync_vector:
            await self._sync_vector_remove(knowledge_id)

        logger.info(f"删除知识条目: {knowledge_id}")
        return True

    async def check_duplicate(
        self,
        db: AsyncSession,
        question: str,
        exclude_id: Optional[str] = None
    ) -> Optional[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.question == question)
        if exclude_id:
            stmt = stmt.where(KnowledgeItem.id != exclude_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_categories(self, db: AsyncSession) -> List[str]:
        stmt = select(KnowledgeItem.category).distinct()
        result = await db.execute(stmt)
        return [row[0] for row in result.fetchall()]

    async def get_total_count(self, db: AsyncSession) -> int:
        stmt = select(func.count(KnowledgeItem.id))
        result = await db.execute(stmt)
        return result.scalar() or 0
    async def delete_by_category(self, db: AsyncSession, category: str) -> int:
        """删除指定分类下的所有知识条目，同步删除向量索引。

        Returns:
            删除的条目数
        """
        stmt = select(KnowledgeItem).where(KnowledgeItem.category == category)
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        count = 0
        for item in items:
            await self._sync_vector_remove(item.id, persist_index=False)
            await db.delete(item)
            count += 1

        if count:
            await db.commit()
            await self.vector_service.save()
            logger.info(f"按分类删除知识条目: category={category}, count={count}")

        return count

    @staticmethod
    async def get_all_knowledge_items(db: AsyncSession) -> List[KnowledgeItem]:
        stmt = select(KnowledgeItem)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ==================== 导入导出 ====================

    async def export_all(self, db: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(KnowledgeItem).order_by(KnowledgeItem.created_at.asc())
        result = await db.execute(stmt)
        items = result.scalars().all()

        return [
            {
                "id": item.id,
                "question": item.question,
                "answer": item.answer,
                "keywords": item.keywords or [],
                "category": item.category,
                "score": item.score,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None
            }
            for item in items
        ]

    async def import_items(
        self,
        db: AsyncSession,
        items: List[Dict[str, Any]],
        skip_duplicates: bool = True,
        sync_vector: bool = True
    ) -> Tuple[int, int, List[str]]:
        success_count = 0
        skip_count = 0
        errors = []

        for idx, item_data in enumerate(items):
            try:
                question = item_data.get("question", "").strip()
                answer = item_data.get("answer", "").strip()

                if not question or not answer:
                    errors.append(f"第{idx + 1}条: 问题或答案为空")
                    continue

                if skip_duplicates:
                    duplicate = await self.check_duplicate(db, question)
                    if duplicate:
                        skip_count += 1
                        continue

                await self.create_knowledge(
                    db=db,
                    question=question,
                    answer=answer,
                    keywords=item_data.get("keywords", []),
                    category=item_data.get("category", "通用"),
                    score=item_data.get("score", 1.0),
                    sync_vector=sync_vector
                )
                success_count += 1

            except Exception as e:
                errors.append(f"第{idx + 1}条: {str(e)}")

        return success_count, skip_count, errors

    # ==================== 向量索引管理（分块） ====================

    def _build_chunks(self, item: KnowledgeItem) -> List[Tuple[str, str]]:
        """将一条知识拆分为多个 chunk，返回 [(chunk_id, chunk_text), ...]。

        短文本（不超过 chunk_size）仍然只产生一个 chunk。
        """
        chunk_size, chunk_overlap, chunk_max = self._get_chunk_config()

        full_text = f"{item.question}\n{item.answer}"
        chunks = chunk_text(full_text, chunk_size, chunk_overlap)

        # 限制每条知识最多 chunk_max 个 chunk
        chunks = chunks[:chunk_max]

        return [
            (make_chunk_id(item.id, idx), text)
            for idx, text in enumerate(chunks)
        ]

    async def _sync_vector_add(
        self,
        item: KnowledgeItem,
        db: AsyncSession = None,
        persist_index: bool = True
    ) -> bool:
        """添加知识条目的所有 chunk 向量到索引"""
        from app.services.performance_service import get_performance_service
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            if db and not self.vector_service._config_synced:
                await self.vector_service.sync_config_from_db(db)

            chunks = self._build_chunks(item)
            any_added = False

            # 批量 embedding
            texts = [text for _, text in chunks]
            embeddings = await self.vector_service.embed_texts(texts)

            if embeddings is None:
                success = False
                return False

            for (chunk_id, _), vector in zip(chunks, embeddings):
                if vector is None:
                    continue
                added = await self.vector_service.add_vector(chunk_id, vector)
                if added:
                    any_added = True

            if any_added and persist_index:
                await self.vector_service.save()
            if not any_added:
                success = False
            return any_added
        except Exception as e:
            success = False
            logger.error(f"添加向量索引失败: {item.id}, {e}")
            return False
        finally:
            duration = _time.perf_counter() - start
            perf.record("knowledge_add", duration, success)

    async def _sync_vector_update(
        self,
        item: KnowledgeItem,
        db: AsyncSession = None,
        persist_index: bool = True
    ) -> bool:
        """更新知识条目的向量索引：先删除旧 chunk，再添加新 chunk"""
        from app.services.performance_service import get_performance_service
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            if db and not self.vector_service._config_synced:
                await self.vector_service.sync_config_from_db(db)

            # 按前缀删除该知识的所有 chunk 向量
            prefix = f"{item.id}{CHUNK_ID_SEP}"
            await self.vector_service.remove_vectors_by_prefix(prefix)
            # 也删除可能存在的旧格式（无 chunk 后缀）向量
            await self.vector_service.remove_vector(item.id)

            # 重新添加
            chunks = self._build_chunks(item)
            texts = [text for _, text in chunks]
            embeddings = await self.vector_service.embed_texts(texts)

            any_added = False
            if embeddings:
                for (chunk_id, _), vector in zip(chunks, embeddings):
                    if vector is None:
                        continue
                    added = await self.vector_service.add_vector(chunk_id, vector)
                    if added:
                        any_added = True

            if persist_index:
                await self.vector_service.save()
            if not any_added:
                success = False
            return any_added
        except Exception as e:
            success = False
            logger.error(f"更新向量索引失败: {item.id}, {e}")
            return False
        finally:
            duration = _time.perf_counter() - start
            perf.record("knowledge_update", duration, success)

    async def _sync_vector_remove(self, knowledge_id: str, persist_index: bool = True) -> bool:
        """从向量索引中删除知识条目的所有 chunk 向量"""
        try:
            # 删除 chunk 格式的向量
            prefix = f"{knowledge_id}{CHUNK_ID_SEP}"
            removed_count = await self.vector_service.remove_vectors_by_prefix(prefix)
            # 也删除可能存在的旧格式（无 chunk 后缀）向量
            removed_old = await self.vector_service.remove_vector(knowledge_id)
            removed = removed_count > 0 or removed_old
            if removed and persist_index:
                await self.vector_service.save()
            return removed
        except Exception as e:
            logger.error(f"删除向量索引失败: {knowledge_id}, {e}")
            return False

    async def rebuild_index(self, db: AsyncSession) -> Tuple[int, List[str]]:
        """重建向量索引（分块模式）"""
        config_ok = await self.vector_service.sync_config_from_db(db)
        if not config_ok:
            if not self.vector_service.is_embedding_available():
                return 0, ["Embedding服务不可用：未配置API密钥，请在设置页面配置Embedding的API密钥"]

        await self.vector_service.clear()

        stmt = select(KnowledgeItem)
        result = await db.execute(stmt)
        items = result.scalars().all()

        if not items:
            await self.vector_service.save()
            return 0, []

        success_count = 0
        errors = []

        for item in items:
            try:
                if await self._sync_vector_add(item, persist_index=False):
                    success_count += 1
                else:
                    errors.append(f"{item.id}: 向量化失败")
            except Exception as e:
                errors.append(f"{item.id}: {str(e)}")

        await self.vector_service.save()

        logger.info(f"重建向量索引完成: 成功 {success_count}, 失败 {len(errors)}")
        return success_count, errors

    def get_index_status(self) -> Dict[str, Any]:
        return {
            "count": self.vector_service.count,
            "dimension": self.vector_service.dimension,
            "embedding_model": self.vector_service.embedding_model,
            "embedding_available": self.vector_service.is_embedding_available(),
            "embedding_dimension": self.vector_service.embedding_dimension if self.vector_service.is_embedding_available() else None
        }

    def check_index_needs_rebuild(self, current_model: Optional[str] = None) -> Tuple[bool, str]:
        return self.vector_service.needs_rebuild(current_model)


# 创建全局服务实例
knowledge_service = KnowledgeService()

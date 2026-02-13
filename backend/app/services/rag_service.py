# -*- coding: utf-8 -*-
"""
RAG服务模块 - 检索增强生成服务

功能:
- 知识检索和上下文构建
- 查询改写
- 多路向量检索 + 关键词覆盖度 bonus
- 倒排索引加速关键词检索
- 置信度计算
"""

import asyncio
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


@dataclass
class RAGSearchResult:
    """RAG搜索结果"""
    query: str = ""
    rewritten_query: str = ""
    retrieved_items: List[Dict[str, Any]] = field(default_factory=list)
    context_text: str = ""
    confidence: float = 0.0
    search_method: str = "vector"  # "vector" or "keyword"
    final_prompt: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "rewritten_query": self.rewritten_query,
            "retrieved_items": self.retrieved_items,
            "context_text": self.context_text,
            "confidence": self.confidence,
            "search_method": self.search_method,
            "final_prompt": self.final_prompt,
        }


# 电商客服场景停用词
STOP_PHRASES = [
    "请问一下", "想问一下", "问一下", "想知道", "我想问", "我想知道",
    "可不可以", "能不能", "怎么样", "好不好",
    "帮我看看", "帮我查查", "帮我问问",
    "麻烦问一下", "麻烦帮我",
    "你好", "您好", "请问", "我想", "帮我", "麻烦",
    "谢谢", "感谢", "好的", "可以吗", "行吗", "好吗",
]

# 电商领域同义词映射
SYNONYM_MAP = {
    "促销活动": "优惠活动", "促销": "优惠活动", "活动": "优惠活动",
    "有什么活动": "优惠活动", "什么活动": "优惠活动",
    "多少钱": "价格", "什么价": "价格", "价位": "价格",
    "贵不贵": "价格", "便宜": "优惠", "打折": "折扣优惠",
    "发货": "物流配送", "快递": "物流", "送货": "配送",
    "到货": "送达", "几天到": "配送时间", "多久到": "配送时间",
    "退货": "退换货", "换货": "退换货", "退款": "退款",
    "保修": "质保", "售后": "售后服务", "维修": "维修",
    "有货吗": "库存", "有没有货": "库存", "缺货": "库存",
    "尺码": "尺寸", "大小": "尺寸",
    "付款": "支付", "怎么付": "支付方式",
    "订单": "订单", "查单": "订单查询",
}


class RAGService:
    """RAG服务类 - 检索增强生成"""

    def __init__(
        self,
        similarity_threshold: float = 0.4,
        retrieval_top_k: int = 5,
        context_max_chars: int = 4000,
        context_top_n: int = 3,
        use_rewrite: bool = True,
    ):
        self.similarity_threshold = similarity_threshold
        self.retrieval_top_k = retrieval_top_k
        self.context_max_chars = context_max_chars
        self.context_top_n = context_top_n
        self.use_rewrite = use_rewrite
        self._vector_service = None
        self._last_result: Optional[RAGSearchResult] = None

    def _get_vector_service(self):
        if self._vector_service is None:
            from app.services.vector_service import VectorService
            self._vector_service = VectorService()
        return self._vector_service

    # ==================== 查询改写 ====================

    def rewrite_query(self, query: str) -> str:
        """查询改写 - 停用词过滤 + 同义词扩展"""
        cleaned_query = query

        for phrase in STOP_PHRASES:
            cleaned_query = cleaned_query.replace(phrase, " ")

        cleaned_query = " ".join(cleaned_query.split()).strip()

        if len(cleaned_query) < 2:
            cleaned_query = query

        expanded_terms = []
        for user_term, search_term in SYNONYM_MAP.items():
            if user_term in query:
                if search_term not in cleaned_query and search_term not in expanded_terms:
                    expanded_terms.append(search_term)

        if expanded_terms:
            return f"{cleaned_query} {' '.join(expanded_terms)}"
        return cleaned_query

    # ==================== Token 提取 ====================

    def _extract_tokens(self, text: str) -> List[str]:
        """提取文本中的 token（英文词 + 中文 bigram）"""
        s = (text or "").strip()
        if not s:
            return []

        tokens: List[str] = []
        s_lower = s.lower()
        tokens.extend(re.findall(r"[a-z0-9]{2,}", s_lower))

        for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s):
            seg = seg.strip()
            if not seg:
                continue
            tokens.append(seg)
            for i in range(min(len(seg) - 1, 12)):
                tokens.append(seg[i:i + 2])

        seen: Set[str] = set()
        uniq: List[str] = []
        for t in tokens:
            if t and t not in seen:
                seen.add(t)
                uniq.append(t)
            if len(uniq) >= 40:
                break
        return uniq

    # ==================== 倒排索引 ====================

    def _build_inverted_index(
        self, knowledge_items: List[Dict[str, Any]]
    ) -> Dict[str, Set[int]]:
        """构建 token → 条目索引位置 的倒排索引，用于关键词检索粗筛。"""
        inverted: Dict[str, Set[int]] = defaultdict(set)
        for idx, item in enumerate(knowledge_items):
            item_text = f"{item.get('question', '')} {item.get('answer', '')}"
            for token in self._extract_tokens(item_text):
                inverted[token].add(idx)
            for kw in item.get("keywords", []):
                if kw:
                    inverted[kw.lower()].add(idx)
        return inverted

    # ==================== 置信度 ====================

    def _compute_confidence(
        self,
        query: str,
        results: List[Tuple[Dict, float]]
    ) -> float:
        if not results:
            return 0.0

        top1 = results[0][1]
        top2 = results[1][1] if len(results) >= 2 else None
        gap = (top1 - top2) if top2 is not None else 0.0

        item = results[0][0]
        keywords = item.get("keywords", [])
        if keywords:
            denom = min(len(keywords), 6)
            hit = sum(1 for kw in keywords[:denom] if kw in query)
            keyword_cover = hit / max(1, denom)
        else:
            keyword_cover = 0.0

        top_k_bonus = (min(len(results), 5) - 1) / 4 if len(results) >= 2 else 0.0

        confidence = top1
        confidence += 0.15 * max(0.0, min(gap, 1.0))
        confidence += 0.08 * max(0.0, min(keyword_cover, 1.0))
        confidence += 0.04 * max(0.0, min(top_k_bonus, 1.0))

        return max(0.0, min(1.0, confidence))

    # ==================== 上下文构建 ====================

    def _build_context(
        self,
        results: List[Tuple[Dict, float]],
        chunk_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """构建上下文文本。

        如果 chunk_map 中有该知识 ID 对应的命中 chunk 片段，
        优先使用 chunk 片段（更精准）；否则回退到整条 question/answer。
        """
        if not results:
            return ""

        context_parts: List[str] = []
        total = 0

        for item, _ in results[:self.context_top_n]:
            item_id = item.get("id", "")
            chunk_snippet = chunk_map.get(item_id) if chunk_map else None

            if chunk_snippet:
                question = item.get("question", "")
                part = f"问题：{question}\n内容：{chunk_snippet}"
            else:
                question = item.get("question", "")
                answer = item.get("answer", "")
                part = f"问题：{question}\n答案：{answer}"

            next_total = total + len(part)
            if self.context_max_chars > 0 and next_total > self.context_max_chars:
                if not context_parts:
                    context_parts.append(part[:self.context_max_chars])
                break

            context_parts.append(part)
            total = next_total

        return "\n\n---\n\n".join(context_parts)

    # ==================== 关键词覆盖度 bonus ====================

    def _keyword_coverage_bonus(
        self,
        query: str,
        item: Dict[str, Any],
    ) -> float:
        """计算关键词覆盖度 bonus，用于向量检索结果的二次排序。

        bonus = 0.2 * (命中关键词数 / min(关键词总数, 3))，上限 0.2。
        """
        keywords = item.get("keywords", [])
        if not keywords:
            return 0.0
        denom = min(len(keywords), 3)
        hits = sum(1 for kw in keywords[:denom] if kw and kw in query)
        return 0.2 * min(hits, denom) / max(1, denom)

    # ==================== 搜索主入口 ====================

    async def search(
        self,
        query: str,
        knowledge_items: List[Dict[str, Any]],
        threshold: float = None
    ) -> RAGSearchResult:
        threshold = self.similarity_threshold if threshold is None else threshold

        result = RAGSearchResult()
        result.query = query
        rewritten = self.rewrite_query(query) if self.use_rewrite else query
        result.rewritten_query = rewritten

        # 多路查询：同时用 rewritten_query 和原始 query 做向量检索
        queries = [rewritten]
        if rewritten != query:
            queries.append(query)

        vector_results, chunk_map = await self._vector_search_multi(
            queries, knowledge_items, threshold
        )

        if vector_results:
            result.search_method = "vector"
            results = vector_results
        else:
            result.search_method = "keyword"
            results = self._keyword_search(
                rewritten, knowledge_items, threshold
            )
            chunk_map = {}

        result.retrieved_items = [
            {"id": item.get("id"), "question": item.get("question"),
             "answer": item.get("answer", ""), "score": score,
             "category": item.get("category", "通用")}
            for item, score in results
        ]

        result.context_text = self._build_context(results, chunk_map)
        result.confidence = self._compute_confidence(query, results)

        self._last_result = result
        return result

    # ==================== 多路向量检索 ====================

    async def _vector_search_multi(
        self,
        queries: List[str],
        knowledge_items: List[Dict[str, Any]],
        threshold: float,
    ) -> Tuple[List[Tuple[Dict, float]], Dict[str, str]]:
        """多路向量检索：对多个 query 分别 embedding + 搜索，
        chunk 级命中聚合回知识条目，加关键词覆盖度 bonus。

        Returns:
            (results, chunk_map)
            - results: [(item_dict, final_score), ...]
            - chunk_map: {knowledge_id: best_chunk_text} 用于上下文构建
        """
        from app.services.performance_service import get_performance_service
        from app.services.knowledge_service import split_chunk_id
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            vector_service = self._get_vector_service()

            if not vector_service.is_embedding_available():
                logger.warning("Embedding服务不可用")
                return [], {}

            candidate_k = self.retrieval_top_k * 3
            item_map = {item.get("id"): item for item in knowledge_items}

            # 聚合：knowledge_id → max_score
            best_scores: Dict[str, float] = {}
            # 记录最佳 chunk 的原始 ID（用于获取 chunk 文本）
            best_chunk_ids: Dict[str, str] = {}

            # 批量 embedding 所有 query
            embeddings = await vector_service.embed_texts(queries)
            if not embeddings:
                return [], {}

            for q_idx, emb in enumerate(embeddings):
                if emb is None:
                    continue
                search_results = await vector_service.search(emb, top_k=candidate_k)
                for raw_id, score in search_results:
                    if score < threshold:
                        continue
                    knowledge_id, _ = split_chunk_id(raw_id)
                    if knowledge_id not in best_scores or score > best_scores[knowledge_id]:
                        best_scores[knowledge_id] = score
                        best_chunk_ids[knowledge_id] = raw_id

            if not best_scores:
                return [], {}

            # 加关键词覆盖度 bonus
            original_query = queries[0]
            scored: List[Tuple[str, float]] = []
            for kid, max_score in best_scores.items():
                item = item_map.get(kid)
                if not item:
                    continue
                bonus = self._keyword_coverage_bonus(original_query, item)
                final_score = min(1.0, max_score + bonus)
                scored.append((kid, final_score))

            scored.sort(key=lambda x: x[1], reverse=True)

            # 构建 chunk_map：knowledge_id → chunk 文本片段
            # 从向量索引的 ID 映射中获取 chunk 文本（这里用知识条目的 answer 截取）
            chunk_map: Dict[str, str] = {}
            results: List[Tuple[Dict, float]] = []
            for kid, score in scored:
                item = item_map.get(kid)
                if not item:
                    continue
                results.append((item, score))
                # 如果命中的是 chunk（含 #chunk_ 分隔符），记录到 chunk_map
                raw_id = best_chunk_ids.get(kid, kid)
                _, chunk_idx = split_chunk_id(raw_id)
                if chunk_idx >= 0:
                    # 重新切分文本获取对应 chunk 片段
                    from app.services.knowledge_service import chunk_text as do_chunk
                    from app.core.config import Config
                    cfg = Config()
                    cs = int(cfg.get("chunk_size", 500))
                    co = int(cfg.get("chunk_overlap", 50))
                    full_text = f"{item.get('question', '')}\n{item.get('answer', '')}"
                    chunks = do_chunk(full_text, cs, co)
                    if chunk_idx < len(chunks):
                        chunk_map[kid] = chunks[chunk_idx]

                if len(results) >= self.retrieval_top_k:
                    break

            return results, chunk_map

        except Exception:
            success = False
            logger.exception("向量检索失败")
            return [], {}
        finally:
            duration = _time.perf_counter() - start
            perf.record("vector_search", duration, success)

    # ==================== 关键词检索（倒排索引） ====================

    def _keyword_search(
        self,
        query: str,
        knowledge_items: List[Dict[str, Any]],
        threshold: float
    ) -> List[Tuple[Dict, float]]:
        """关键词检索 — 先用倒排索引粗筛候选，再对候选算分。"""
        from app.services.performance_service import get_performance_service
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            query_tokens = set(self._extract_tokens(query))
            if not query_tokens:
                return []

            # 构建倒排索引
            inverted = self._build_inverted_index(knowledge_items)

            # 粗筛：只保留至少有一个 token 命中的候选
            candidate_indices: Set[int] = set()
            for token in query_tokens:
                if token in inverted:
                    candidate_indices.update(inverted[token])

            if not candidate_indices:
                return []

            results = []

            for idx in candidate_indices:
                item = knowledge_items[idx]
                item_text = f"{item.get('question', '')} {item.get('answer', '')}"
                item_tokens = set(self._extract_tokens(item_text))

                for kw in item.get("keywords", []):
                    if kw:
                        item_tokens.add(kw.lower())

                if not item_tokens:
                    continue

                intersection = query_tokens & item_tokens
                if not intersection:
                    continue

                # Jaccard 相似度
                score = len(intersection) / len(query_tokens | item_tokens)

                # 关键词命中加分
                keywords = item.get("keywords", [])
                kw_hits = sum(1 for kw in keywords if kw and kw.lower() in query.lower())
                if kw_hits > 0:
                    score += 0.2 * min(kw_hits, 3) / 3

                score = min(1.0, score)

                if score >= threshold:
                    results.append((item, score))

            results.sort(key=lambda x: x[1], reverse=True)
            return results[:self.retrieval_top_k]
        except Exception:
            success = False
            raise
        finally:
            duration = _time.perf_counter() - start
            perf.record("keyword_search", duration, success)

    # ==================== Prompt 构建 ====================

    def build_system_prompt(self, context_text: Optional[str] = None) -> str:
        base_prompt = (
            "你是一个专业的电商客服助手，负责解答用户关于商品、订单、物流、退换货等问题。"
            "请用友好、专业的语气回复，回答要简洁有帮助。"
        )

        if context_text:
            return (
                f"{base_prompt}\n\n"
                "以下是从知识库中检索到的相关信息，请参考这些信息来回答用户问题：\n\n"
                "---知识库内容开始---\n"
                f"{context_text}\n"
                "---知识库内容结束---\n\n"
                "请基于上述知识库内容回答用户问题。如果知识库内容不足以回答问题，可以适当补充，但要保持专业和准确。"
            )
        return base_prompt

    def build_messages(
        self,
        user_message: str,
        context_text: Optional[str] = None,
        history: Optional[List[Dict]] = None
    ) -> List[Dict]:
        messages = [{"role": "system", "content": self.build_system_prompt(context_text)}]

        if history:
            for msg in history:
                role = msg.get("role")
                content = msg.get("content")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": str(content)})

        messages.append({"role": "user", "content": user_message})
        return messages

    @property
    def last_result(self) -> Optional[RAGSearchResult]:
        return self._last_result

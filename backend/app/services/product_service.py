# -*- coding: utf-8 -*-
"""
商品服务模块 - Product Service

功能:
- 商品CRUD操作
- 知识库同步
- 导入导出
"""

import uuid
import logging
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.knowledge import KnowledgeItem
from app.services.knowledge_service import knowledge_service
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def generate_product_id() -> str:
    """生成唯一商品ID"""
    return f"prod_{uuid.uuid4().hex[:12]}"


class ProductService:
    """商品服务类"""
    
    # ==================== CRUD操作 ====================
    
    async def create_product(
        self,
        db: AsyncSession,
        name: str,
        price: float,
        category: str = "通用",
        description: str = "",
        specifications: Optional[Dict[str, str]] = None,
        stock: int = 0,
        keywords: Optional[List[str]] = None,
        sync_knowledge: bool = True
    ) -> Product:
        """
        创建商品
        
        Args:
            db: 数据库会话
            name: 商品名称
            price: 价格
            category: 分类
            description: 描述
            specifications: 规格参数
            stock: 库存
            keywords: 关键词
            sync_knowledge: 是否同步知识库
        
        Returns:
            新创建的商品
        """
        product_id = generate_product_id()
        
        product = Product(
            id=product_id,
            name=name,
            price=price,
            category=category,
            description=description,
            specifications=specifications or {},
            stock=stock,
            keywords=keywords or [],
            created_at=utcnow(),
            updated_at=utcnow()
        )
        
        db.add(product)
        await db.commit()
        await db.refresh(product)
        
        # 同步知识库
        if sync_knowledge:
            await self._sync_knowledge_add(db, product)
        
        logger.info(f"创建商品: {product_id}")
        return product

    async def get_product(
        self,
        db: AsyncSession,
        product_id: str
    ) -> Optional[Product]:
        """
        获取商品
        
        Args:
            db: 数据库会话
            product_id: 商品ID
        
        Returns:
            商品或None
        """
        stmt = select(Product).where(Product.id == product_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_product_list(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        keyword: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        in_stock: Optional[bool] = None
    ) -> Tuple[List[Product], int]:
        """
        获取商品列表（分页、筛选）
        
        Args:
            db: 数据库会话
            page: 页码（从1开始）
            page_size: 每页数量
            category: 分类筛选
            keyword: 关键词筛选
            min_price: 最低价格
            max_price: 最高价格
            in_stock: 是否有库存
        
        Returns:
            (商品列表, 总数)
        """
        stmt = select(Product)
        count_stmt = select(func.count(Product.id))
        
        # 分类筛选
        if category:
            stmt = stmt.where(Product.category == category)
            count_stmt = count_stmt.where(Product.category == category)
        
        # 关键词筛选（搜索名称和描述）
        if keyword:
            search_pattern = f"%{keyword}%"
            keyword_filter = or_(
                Product.name.ilike(search_pattern),
                Product.description.ilike(search_pattern)
            )
            stmt = stmt.where(keyword_filter)
            count_stmt = count_stmt.where(keyword_filter)
        
        # 价格范围筛选
        if min_price is not None:
            stmt = stmt.where(Product.price >= min_price)
            count_stmt = count_stmt.where(Product.price >= min_price)
        
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)
            count_stmt = count_stmt.where(Product.price <= max_price)
        
        # 库存状态筛选
        if in_stock is not None:
            if in_stock:
                stmt = stmt.where(Product.stock > 0)
                count_stmt = count_stmt.where(Product.stock > 0)
            else:
                stmt = stmt.where(Product.stock == 0)
                count_stmt = count_stmt.where(Product.stock == 0)
        
        # 按更新时间降序排列
        stmt = stmt.order_by(Product.updated_at.desc())
        
        # 分页
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        # 执行查询
        result = await db.execute(stmt)
        items = list(result.scalars().all())
        
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return items, total
    
    async def update_product(
        self,
        db: AsyncSession,
        product_id: str,
        name: Optional[str] = None,
        price: Optional[float] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        specifications: Optional[Dict[str, str]] = None,
        stock: Optional[int] = None,
        keywords: Optional[List[str]] = None,
        sync_knowledge: bool = True
    ) -> Optional[Product]:
        """
        更新商品
        
        Args:
            db: 数据库会话
            product_id: 商品ID
            name: 新名称
            price: 新价格
            category: 新分类
            description: 新描述
            specifications: 新规格
            stock: 新库存
            keywords: 新关键词
            sync_knowledge: 是否同步知识库
        
        Returns:
            更新后的商品或None
        """
        product = await self.get_product(db, product_id)
        if not product:
            return None
        
        # 记录是否需要更新知识库
        need_knowledge_update = False
        
        if name is not None:
            product.name = name
            need_knowledge_update = True
        if price is not None:
            product.price = price
            need_knowledge_update = True
        if category is not None:
            product.category = category
            need_knowledge_update = True
        if description is not None:
            product.description = description
            need_knowledge_update = True
        if specifications is not None:
            product.specifications = specifications
            need_knowledge_update = True
        if stock is not None:
            product.stock = stock
            need_knowledge_update = True
        if keywords is not None:
            product.keywords = keywords
        
        product.updated_at = utcnow()
        
        await db.commit()
        await db.refresh(product)
        
        # 同步知识库
        if sync_knowledge and need_knowledge_update:
            await self._sync_knowledge_update(db, product)
        
        logger.info(f"更新商品: {product_id}")
        return product
    
    async def delete_product(
        self,
        db: AsyncSession,
        product_id: str,
        sync_knowledge: bool = True
    ) -> bool:
        """
        删除商品
        
        Args:
            db: 数据库会话
            product_id: 商品ID
            sync_knowledge: 是否同步知识库
        
        Returns:
            是否删除成功
        """
        product = await self.get_product(db, product_id)
        if not product:
            return False
        
        # 先同步删除知识库（需要商品信息）
        if sync_knowledge:
            await self._sync_knowledge_remove(db, product_id)
        
        await db.delete(product)
        await db.commit()
        
        logger.info(f"删除商品: {product_id}")
        return True

    async def get_categories(self, db: AsyncSession) -> List[str]:
        """
        获取所有商品分类
        
        Args:
            db: 数据库会话
        
        Returns:
            分类列表
        """
        stmt = select(Product.category).distinct()
        result = await db.execute(stmt)
        return [row[0] for row in result.fetchall() if row[0]]
    
    async def get_total_count(self, db: AsyncSession) -> int:
        """
        获取商品总数
        
        Args:
            db: 数据库会话
        
        Returns:
            总数
        """
        stmt = select(func.count(Product.id))
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def delete_by_category(self, db: AsyncSession, category: str) -> int:
        """删除指定分类下的所有商品，同步删除知识库条目。

        Returns:
            删除的商品数
        """
        stmt = select(Product).where(Product.category == category)
        result = await db.execute(stmt)
        products = list(result.scalars().all())

        count = 0
        for product in products:
            await self._sync_knowledge_remove(db, product.id)
            await db.delete(product)
            count += 1

        if count:
            await db.commit()
            logger.info(f"按分类删除商品: category={category}, count={count}")

        return count

    
    # ==================== 导入导出 ====================
    
    async def export_all(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        导出所有商品
        
        Args:
            db: 数据库会话
        
        Returns:
            商品列表（字典格式）
        """
        stmt = select(Product).order_by(Product.created_at.asc())
        result = await db.execute(stmt)
        items = result.scalars().all()
        
        return [
            {
                "id": item.id,
                "name": item.name,
                "price": item.price,
                "category": item.category,
                "description": item.description,
                "specifications": item.specifications or {},
                "stock": item.stock,
                "keywords": item.keywords or [],
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
        sync_knowledge: bool = True
    ) -> Tuple[int, int, List[str]]:
        """
        批量导入商品
        
        Args:
            db: 数据库会话
            items: 商品列表
            skip_duplicates: 是否跳过重复项（按名称判断）
            sync_knowledge: 是否同步知识库
        
        Returns:
            (成功数, 跳过数, 错误列表)
        """
        success_count = 0
        skip_count = 0
        errors = []
        
        for idx, item_data in enumerate(items):
            try:
                name = item_data.get("name", "").strip()
                price = item_data.get("price")
                
                if not name:
                    errors.append(f"第{idx + 1}条: 商品名称为空")
                    continue
                
                if price is None or price < 0:
                    errors.append(f"第{idx + 1}条: 价格无效")
                    continue
                
                # 检查重复（按名称）
                if skip_duplicates:
                    duplicate = await self.check_duplicate_name(db, name)
                    if duplicate:
                        skip_count += 1
                        continue
                
                # 创建商品
                await self.create_product(
                    db=db,
                    name=name,
                    price=float(price),
                    category=item_data.get("category", "通用"),
                    description=item_data.get("description", ""),
                    specifications=item_data.get("specifications", {}),
                    stock=item_data.get("stock", 0),
                    keywords=item_data.get("keywords", []),
                    sync_knowledge=sync_knowledge
                )
                success_count += 1
                
            except Exception as e:
                errors.append(f"第{idx + 1}条: {str(e)}")
        
        return success_count, skip_count, errors
    
    async def check_duplicate_name(
        self,
        db: AsyncSession,
        name: str,
        exclude_id: Optional[str] = None
    ) -> Optional[Product]:
        """
        检查重复商品名称
        
        Args:
            db: 数据库会话
            name: 商品名称
            exclude_id: 排除的ID（用于更新时检查）
        
        Returns:
            重复的商品或None
        """
        stmt = select(Product).where(Product.name == name)
        
        if exclude_id:
            stmt = stmt.where(Product.id != exclude_id)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ==================== 知识库同步 ====================

    @staticmethod
    def _make_product_kb_id(product_id: str, index: int) -> str:
        """生成商品对应的知识库条目 ID（稳定、可按前缀删除）。

        格式: ``pkb_{product_id}_0``, ``pkb_{product_id}_1``, ...
        """
        return f"pkb_{product_id}_{index}"

    @staticmethod
    def _product_kb_prefix(product_id: str) -> str:
        """返回某商品所有知识条目 ID 的公共前缀。"""
        return f"pkb_{product_id}_"

    def _build_product_qa_pairs(self, product: Product) -> List[Dict[str, str]]:
        """为商品生成多条问答知识，提升检索召回率。

        Returns:
            [{"question": ..., "answer": ...}, ...]
        """
        pairs: List[Dict[str, str]] = []
        stock_status = "有货" if product.stock > 0 else "缺货"

        # 1. 综合信息
        answer_parts = [
            f"商品名称：{product.name}",
            f"价格：¥{product.price:.2f}",
            f"分类：{product.category}",
            f"库存状态：{stock_status}（{product.stock}件）",
        ]
        if product.description:
            answer_parts.append(f"商品描述：{product.description}")
        if product.specifications:
            specs_str = "、".join(f"{k}: {v}" for k, v in product.specifications.items())
            answer_parts.append(f"规格参数：{specs_str}")

        pairs.append({
            "question": f"{product.name}的详细信息是什么？",
            "answer": "\n".join(answer_parts),
        })

        # 2. 价格
        pairs.append({
            "question": f"{product.name}多少钱？{product.name}的价格是多少？",
            "answer": f"{product.name}的价格是 ¥{product.price:.2f}。",
        })

        # 3. 库存
        stock_label = "有货" if product.stock > 0 else "暂时缺货"
        pairs.append({
            "question": f"{product.name}有货吗？{product.name}还有库存吗？",
            "answer": f"{product.name}目前{stock_label}，库存 {product.stock} 件。",
        })

        # 4. 规格（如果有）
        if product.specifications:
            specs_str = "、".join(f"{k}: {v}" for k, v in product.specifications.items())
            pairs.append({
                "question": f"{product.name}的规格参数是什么？{product.name}有哪些参数？",
                "answer": f"{product.name}的规格参数：{specs_str}。",
            })

        # 5. 描述（如果有）
        if product.description:
            pairs.append({
                "question": f"{product.name}怎么样？介绍一下{product.name}。",
                "answer": f"{product.name}：{product.description}",
            })

        return pairs

    async def _sync_knowledge_add(self, db: AsyncSession, product: Product) -> bool:
        """添加商品到知识库（使用稳定 ID）"""
        from app.services.performance_service import get_performance_service
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            qa_pairs = self._build_product_qa_pairs(product)
            keywords = list(product.keywords or []) + [product.name, product.category]

            for idx, pair in enumerate(qa_pairs):
                kb_id = self._make_product_kb_id(product.id, idx)
                await knowledge_service.create_knowledge(
                    db=db,
                    question=pair["question"],
                    answer=pair["answer"],
                    keywords=keywords,
                    category=f"商品-{product.category}",
                    score=1.0,
                    sync_vector=True,
                    knowledge_id=kb_id,
                )

            logger.info(f"同步商品到知识库: {product.id} ({len(qa_pairs)} 条)")
            return True
        except Exception as e:
            success = False
            logger.error(f"同步商品到知识库失败: {product.id}, {e}")
            return False
        finally:
            duration = _time.perf_counter() - start
            perf.record("product_add", duration, success)

    async def _sync_knowledge_update(self, db: AsyncSession, product: Product) -> bool:
        """更新商品的知识库条目（按稳定 ID 前缀删除旧条目，重新生成）"""
        from app.services.performance_service import get_performance_service
        import time as _time
        perf = get_performance_service()
        start = _time.perf_counter()
        success = True
        try:
            await self._sync_knowledge_remove(db, product.id)
            await self._sync_knowledge_add(db, product)
            logger.info(f"更新商品知识库: {product.id}")
            return True
        except Exception as e:
            success = False
            logger.error(f"更新商品知识库失败: {product.id}, {e}")
            return False
        finally:
            duration = _time.perf_counter() - start
            perf.record("product_update", duration, success)

    async def _sync_knowledge_remove(self, db: AsyncSession, product_id: str) -> bool:
        """按稳定 ID 前缀删除商品的所有知识条目（不依赖商品名/分类）。"""
        try:
            prefix = self._product_kb_prefix(product_id)
            stmt = select(KnowledgeItem).where(
                KnowledgeItem.id.like(f"{prefix}%")
            )
            result = await db.execute(stmt)
            items = result.scalars().all()

            for item in items:
                await knowledge_service.delete_knowledge(db, item.id, sync_vector=True)

            if items:
                logger.info(f"删除商品知识库条目: {product_id} ({len(items)} 条)")

            return True
        except Exception as e:
            logger.error(f"删除商品知识库条目失败: {product_id}, {e}")
            return False


# 创建全局服务实例
product_service = ProductService()

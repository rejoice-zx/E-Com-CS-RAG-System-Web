# -*- coding: utf-8 -*-
"""
商品API端点 - Product API

功能:
- 商品CRUD操作
- 分页和筛选
- 导入导出
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import json

from app.database import get_db
from app.api.dependencies import CSOrAdminRequired
from app.models.user import User
from app.services.product_service import product_service
from app.schemas.product import (
    CreateProductRequest,
    UpdateProductRequest,
    ProductResponse,
    ProductListResponse,
    ImportProductRequest,
    ImportProductResponse,
    ExportProductResponse
)

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def get_product_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    category: Optional[str] = Query(None, description="分类筛选"),
    keyword: Optional[str] = Query(None, description="关键词筛选"),
    min_price: Optional[float] = Query(None, ge=0, description="最低价格"),
    max_price: Optional[float] = Query(None, ge=0, description="最高价格"),
    in_stock: Optional[bool] = Query(None, description="是否有库存"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    获取商品列表（分页、筛选）
    
    - 需要管理员或客服权限
    - 支持按分类、关键词、价格范围、库存状态筛选
    """
    items, total = await product_service.get_product_list(
        db=db,
        page=page,
        page_size=page_size,
        category=category,
        keyword=keyword,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock
    )
    
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: CreateProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    添加商品
    
    - 需要管理员或客服权限
    - 自动同步知识库
    """
    product = await product_service.create_product(
        db=db,
        name=request.name,
        price=request.price,
        category=request.category,
        description=request.description,
        specifications=request.specifications,
        stock=request.stock,
        keywords=request.keywords
    )
    
    return ProductResponse.model_validate(product)


@router.get("/categories/list")
async def get_product_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """获取商品所有分类"""
    cats = await product_service.get_categories(db)
    return {"categories": cats}


@router.delete("/by-category/{category}", status_code=status.HTTP_200_OK)
async def delete_products_by_category(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    删除指定分类下的所有商品

    - 需要管理员或客服权限
    - 自动同步知识库
    """
    count = await product_service.delete_by_category(db, category)
    return {"deleted_count": count, "category": category}


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    获取商品详情
    
    - 需要管理员或客服权限
    """
    product = await product_service.get_product(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商品不存在"
        )
    
    return ProductResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    request: UpdateProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    更新商品
    
    - 需要管理员或客服权限
    - 自动同步知识库
    """
    # 检查是否存在
    existing = await product_service.get_product(db, product_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商品不存在"
        )
    
    product = await product_service.update_product(
        db=db,
        product_id=product_id,
        name=request.name,
        price=request.price,
        category=request.category,
        description=request.description,
        specifications=request.specifications,
        stock=request.stock,
        keywords=request.keywords
    )
    
    return ProductResponse.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    删除商品
    
    - 需要管理员或客服权限
    - 自动同步知识库
    """
    success = await product_service.delete_product(db, product_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商品不存在"
        )
    
    return None



# ==================== 导入导出 ====================


@router.post("/sync-knowledge")
async def sync_all_products_to_knowledge(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    同步所有商品到知识库（SSE 流式进度）

    - 需要管理员或客服权限
    - 使用稳定 ID，已存在的会自动覆盖
    - 返回 SSE 事件流，前端可实时展示进度
    """
    from sqlalchemy import select
    from app.models.product import Product as ProductModel

    result = await db.execute(select(ProductModel).order_by(ProductModel.created_at.asc()))
    products = list(result.scalars().all())

    total = len(products)

    async def event_stream():
        success_count = 0
        fail_count = 0
        errors: list[str] = []

        # 开始事件
        yield f"data: {json.dumps({'type': 'start', 'total': total}, ensure_ascii=False)}\n\n"

        for idx, product in enumerate(products):
            current = idx + 1
            try:
                await product_service._sync_knowledge_remove(db, product.id)
                ok = await product_service._sync_knowledge_add(db, product)
                if ok:
                    success_count += 1
                    yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'name': product.name, 'status': 'success'}, ensure_ascii=False)}\n\n"
                else:
                    fail_count += 1
                    msg = f"{product.name}: 向量化失败（请检查 Embedding 配置）"
                    errors.append(msg)
                    yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'name': product.name, 'status': 'fail', 'error': msg}, ensure_ascii=False)}\n\n"
            except Exception as e:
                fail_count += 1
                msg = f"{product.name}: {str(e)}"
                errors.append(msg)
                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'name': product.name, 'status': 'fail', 'error': msg}, ensure_ascii=False)}\n\n"

        # 完成事件
        yield f"data: {json.dumps({'type': 'done', 'success_count': success_count, 'fail_count': fail_count, 'total': total, 'errors': errors}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/import", response_model=ImportProductResponse)
async def import_products(
    request: ImportProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    批量导入商品
    
    - 需要管理员或客服权限
    - 支持跳过重复项（按名称判断）
    """
    success_count, skip_count, errors = await product_service.import_items(
        db=db,
        items=[item.model_dump() for item in request.items],
        skip_duplicates=request.skip_duplicates
    )
    
    return ImportProductResponse(
        success_count=success_count,
        skip_count=skip_count,
        errors=errors
    )


@router.get("/export/all", response_model=ExportProductResponse)
async def export_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(CSOrAdminRequired)
):
    """
    导出所有商品
    
    - 需要管理员或客服权限
    """
    items = await product_service.export_all(db)
    
    return ExportProductResponse(
        items=items,
        total=len(items)
    )

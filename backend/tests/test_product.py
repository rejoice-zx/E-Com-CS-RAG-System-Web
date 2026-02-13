# -*- coding: utf-8 -*-
"""
商品模块测试 - Product Module Tests
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product_service import ProductService, product_service


class TestProductCRUD:
    """商品CRUD操作测试"""
    
    @pytest.mark.asyncio
    async def test_create_product(self, test_session: AsyncSession):
        """测试创建商品"""
        service = ProductService()
        
        product = await service.create_product(
            db=test_session,
            name="测试商品",
            price=99.99,
            category="电子产品",
            description="这是一个测试商品",
            specifications={"颜色": "黑色", "尺寸": "中"},
            stock=100,
            keywords=["测试", "商品"],
            sync_knowledge=False
        )
        
        assert product is not None
        assert product.id.startswith("prod_")
        assert product.name == "测试商品"
        assert product.price == 99.99
        assert product.category == "电子产品"
        assert product.stock == 100
        assert product.is_out_of_stock is False
    
    @pytest.mark.asyncio
    async def test_create_product_default_values(self, test_session: AsyncSession):
        """测试创建商品默认值"""
        service = ProductService()
        
        product = await service.create_product(
            db=test_session,
            name="简单商品",
            price=50.0,
            sync_knowledge=False
        )
        
        assert product.category == "通用"
        assert product.description == ""
        assert product.specifications == {}
        assert product.stock == 0
        assert product.keywords == []
        assert product.is_out_of_stock is True
    
    @pytest.mark.asyncio
    async def test_get_product(self, test_session: AsyncSession):
        """测试获取商品"""
        service = ProductService()
        
        created = await service.create_product(
            db=test_session,
            name="获取测试商品",
            price=100.0,
            sync_knowledge=False
        )
        
        retrieved = await service.get_product(test_session, created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "获取测试商品"
    
    @pytest.mark.asyncio
    async def test_get_product_not_found(self, test_session: AsyncSession):
        """测试获取不存在的商品"""
        service = ProductService()
        
        result = await service.get_product(test_session, "nonexistent_id")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_product_list_pagination(self, test_session: AsyncSession):
        """测试商品列表分页"""
        service = ProductService()
        
        for i in range(5):
            await service.create_product(
                db=test_session,
                name=f"分页商品{i}",
                price=10.0 * (i + 1),
                sync_knowledge=False
            )
        
        items, total = await service.get_product_list(
            db=test_session,
            page=1,
            page_size=3
        )
        
        assert len(items) == 3
        assert total == 5
    
    @pytest.mark.asyncio
    async def test_get_product_list_filter_category(self, test_session: AsyncSession):
        """测试按分类筛选商品"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="电子商品1",
            price=100.0,
            category="电子产品",
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="服装商品1",
            price=50.0,
            category="服装",
            sync_knowledge=False
        )
        
        items, total = await service.get_product_list(
            db=test_session,
            category="电子产品"
        )
        
        assert total == 1
        assert items[0].category == "电子产品"

    @pytest.mark.asyncio
    async def test_get_product_list_filter_price_range(self, test_session: AsyncSession):
        """测试按价格范围筛选商品"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="便宜商品",
            price=10.0,
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="中等商品",
            price=50.0,
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="贵商品",
            price=100.0,
            sync_knowledge=False
        )
        
        items, total = await service.get_product_list(
            db=test_session,
            min_price=30.0,
            max_price=80.0
        )
        
        assert total == 1
        assert items[0].name == "中等商品"
    
    @pytest.mark.asyncio
    async def test_get_product_list_filter_stock(self, test_session: AsyncSession):
        """测试按库存状态筛选商品"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="有货商品",
            price=100.0,
            stock=10,
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="缺货商品",
            price=50.0,
            stock=0,
            sync_knowledge=False
        )
        
        items, total = await service.get_product_list(
            db=test_session,
            in_stock=True
        )
        
        assert total == 1
        assert items[0].name == "有货商品"
        
        items, total = await service.get_product_list(
            db=test_session,
            in_stock=False
        )
        
        assert total == 1
        assert items[0].name == "缺货商品"
    
    @pytest.mark.asyncio
    async def test_update_product(self, test_session: AsyncSession):
        """测试更新商品"""
        service = ProductService()
        
        product = await service.create_product(
            db=test_session,
            name="原始商品",
            price=100.0,
            sync_knowledge=False
        )
        
        updated = await service.update_product(
            db=test_session,
            product_id=product.id,
            name="更新后商品",
            price=150.0,
            stock=50,
            sync_knowledge=False
        )
        
        assert updated is not None
        assert updated.name == "更新后商品"
        assert updated.price == 150.0
        assert updated.stock == 50
    
    @pytest.mark.asyncio
    async def test_delete_product(self, test_session: AsyncSession):
        """测试删除商品"""
        service = ProductService()
        
        product = await service.create_product(
            db=test_session,
            name="待删除商品",
            price=100.0,
            sync_knowledge=False
        )
        
        success = await service.delete_product(
            db=test_session,
            product_id=product.id,
            sync_knowledge=False
        )
        
        assert success is True
        
        deleted = await service.get_product(test_session, product.id)
        assert deleted is None
    
    @pytest.mark.asyncio
    async def test_delete_product_not_found(self, test_session: AsyncSession):
        """测试删除不存在的商品"""
        service = ProductService()
        
        success = await service.delete_product(
            db=test_session,
            product_id="nonexistent_id",
            sync_knowledge=False
        )
        
        assert success is False


class TestImportExport:
    """导入导出测试"""
    
    @pytest.mark.asyncio
    async def test_export_all(self, test_session: AsyncSession):
        """测试导出所有商品"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="导出商品1",
            price=100.0,
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="导出商品2",
            price=200.0,
            sync_knowledge=False
        )
        
        items = await service.export_all(test_session)
        
        assert len(items) == 2
        assert all("id" in item for item in items)
        assert all("name" in item for item in items)
        assert all("price" in item for item in items)
    
    @pytest.mark.asyncio
    async def test_import_items(self, test_session: AsyncSession):
        """测试批量导入商品"""
        service = ProductService()
        
        items = [
            {"name": "导入商品1", "price": 100.0, "category": "电子产品"},
            {"name": "导入商品2", "price": 200.0, "category": "服装"},
        ]
        
        success, skip, errors = await service.import_items(
            db=test_session,
            items=items,
            sync_knowledge=False
        )
        
        assert success == 2
        assert skip == 0
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_import_skip_duplicates(self, test_session: AsyncSession):
        """测试导入跳过重复项"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="已存在商品",
            price=100.0,
            sync_knowledge=False
        )
        
        items = [
            {"name": "已存在商品", "price": 150.0},
            {"name": "新商品", "price": 200.0},
        ]
        
        success, skip, errors = await service.import_items(
            db=test_session,
            items=items,
            skip_duplicates=True,
            sync_knowledge=False
        )
        
        assert success == 1
        assert skip == 1
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_import_invalid_data(self, test_session: AsyncSession):
        """测试导入无效数据"""
        service = ProductService()
        
        items = [
            {"name": "", "price": 100.0},
            {"name": "有效商品", "price": -10.0},
        ]
        
        success, skip, errors = await service.import_items(
            db=test_session,
            items=items,
            sync_knowledge=False
        )
        
        assert success == 0
        assert len(errors) == 2


class TestCategories:
    """分类相关测试"""
    
    @pytest.mark.asyncio
    async def test_get_categories(self, test_session: AsyncSession):
        """测试获取所有分类"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="电子商品",
            price=100.0,
            category="电子产品",
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="服装商品",
            price=50.0,
            category="服装",
            sync_knowledge=False
        )
        
        categories = await service.get_categories(test_session)
        
        assert "电子产品" in categories
        assert "服装" in categories
    
    @pytest.mark.asyncio
    async def test_get_total_count(self, test_session: AsyncSession):
        """测试获取商品总数"""
        service = ProductService()
        
        await service.create_product(
            db=test_session,
            name="商品1",
            price=100.0,
            sync_knowledge=False
        )
        await service.create_product(
            db=test_session,
            name="商品2",
            price=200.0,
            sync_knowledge=False
        )
        
        count = await service.get_total_count(test_session)
        
        assert count == 2


class TestOutOfStockStatus:
    """库存状态测试"""
    
    @pytest.mark.asyncio
    async def test_out_of_stock_when_zero(self, test_session: AsyncSession):
        """测试库存为0时标记为缺货"""
        service = ProductService()
        
        product = await service.create_product(
            db=test_session,
            name="缺货商品",
            price=100.0,
            stock=0,
            sync_knowledge=False
        )
        
        assert product.is_out_of_stock is True
    
    @pytest.mark.asyncio
    async def test_in_stock_when_positive(self, test_session: AsyncSession):
        """测试库存大于0时不标记为缺货"""
        service = ProductService()
        
        product = await service.create_product(
            db=test_session,
            name="有货商品",
            price=100.0,
            stock=10,
            sync_knowledge=False
        )
        
        assert product.is_out_of_stock is False

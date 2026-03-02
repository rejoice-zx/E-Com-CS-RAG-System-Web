# 项目文件大小分析报告

> 分析时间：2026-03-01

## 📊 总览

| 项目 | 大小 | 文件数 |
|------|------|--------|
| **项目总计（含 .git）** | **~287 MB** | **~16,400+** |
| 项目总计（不含 .git） | 215.15 MB | 15,444 |

## 📁 各目录大小

| 目录 | 大小 | 文件数 | 说明 |
|------|------|--------|------|
| `frontend/node_modules/` | **205.19 MB** | 15,140 | ⚠️ **最大占用，可删除** |
| `.git/` | **71.53 MB** | 1,007 | ⚠️ Git 历史数据，可清理 |
| `backend/` | 4.38 MB | 210 | ✅ 正常 |
| `image/` | 1.98 MB | 10 | ✅ 项目截图 |
| `frontend/dist/` | ~0.5 MB | 少量 | ⚠️ 构建产物，可删除 |
| `.kiro/` | 0.05 MB | 3 | 可删除 |
| `.pytest_cache/` | ~0.02 MB | 10 | 可删除 |

## 🔍 主要文件类型占用

| 文件类型 | 大小 | 文件数 | 说明 |
|----------|------|--------|------|
| `.js` | 71.47 MB | 5,010 | 主要在 node_modules |
| `.map` | 70.08 MB | 2,825 | Source Map 文件 |
| `.exe` | 20.30 MB | 2 | esbuild 可执行文件 |
| `.ts` | 18.28 MB | 5,114 | TypeScript 类型声明 |
| `.mjs` | 12.02 MB | 1,430 | ES Module 文件 |
| `.json` | 5.54 MB | 163 | package.json 等 |
| `.db` | 1.54 MB | 13 | SQLite 数据库文件 |
| `.pyc` | 1.05 MB | 95 | Python 编译缓存 |

---

## 🧹 清理建议

### 1. `frontend/node_modules/` — 可节省 **~205 MB**

> [!IMPORTANT]
> 这是项目体积最大的来源，占总体积的 **95%+**。

`node_modules` 是 npm 包安装目录，**不需要保留在项目中**。重新安装只需运行：

```bash
cd frontend
npm install
```

**建议操作**：删除 `frontend/node_modules/` 目录。`.gitignore` 已正确配置忽略此目录，不会影响 Git 仓库。

### 2. `frontend/dist/` — 可节省 **~0.5 MB**

构建产物目录，可随时通过 `npm run build` 重新生成。`.gitignore` 已配置忽略。

### 3. `.git/` 历史清理 — 可节省 **~50+ MB**

`.git` 目录占 71.53 MB，可能是因为历史提交中包含了大文件（如之前的 `node_modules` 或数据文件被误提交过）。

**清理方法**（谨慎操作）：

```bash
# 查看哪些文件占用 git 历史空间
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '/^blob/ {print $3,$4}' | sort -rn | head -20

# 或者使用 git gc 压缩
git gc --aggressive --prune=now
```

### 4. `backend/data/` 中的测试数据库 — 可节省 **~0.8 MB**

包含 10 个 `audit_*.db` 测试数据库文件（每个 86 KB），还有 2 个备份文件：

| 文件 | 大小 | 建议 |
|------|------|------|
| `app.db` | 585 KB | ✅ 保留（主数据库） |
| `vectors.index` | 1.2 MB | ✅ 保留（向量索引） |
| `vectors_map.json` | 18 KB | ✅ 保留 |
| `audit_*.db` (10个) | 各 86 KB | ❌ 可删除（测试产物） |
| `backups/` (2组) | ~0.17 MB | ❌ 可删除（旧备份） |

> [!NOTE]
> `.gitignore` 已配置忽略 `backend/data/`，这些文件不会被提交到 Git。

### 5. 缓存目录 — 可节省 **~1 MB**

| 目录 | 说明 | 建议 |
|------|------|------|
| `__pycache__/` (多处) | Python 字节码缓存 | 可删除，运行时自动重建 |
| `.pytest_cache/` (2处) | pytest 测试缓存 | 可删除 |
| `backend/.tmp/` | pytest 临时文件 | 可删除 |
| `.kiro/` | Kiro IDE 配置 | 如不用可删除 |

### 6. `.gitignore` 补充建议

当前 `.gitignore` 缺少以下条目，建议补充：

```gitignore
# 临时文件
backend/.tmp/

# Python 缓存（更全面的匹配）
**/__pycache__/

# 项目文档/不需要的目录
.kiro/
```

---

## ✅ 推荐清理操作总结

| 操作 | 预计节省 | 风险 | 可恢复性 |
|------|----------|------|----------|
| 删除 `frontend/node_modules/` | ~205 MB | 无 | `npm install` 恢复 |
| 删除 `frontend/dist/` | ~0.5 MB | 无 | `npm run build` 恢复 |
| 删除 `audit_*.db` 测试数据 | ~0.8 MB | 低 | 重跑测试恢复 |
| 删除缓存目录 | ~1 MB | 无 | 自动重建 |
| Git 历史清理 | ~50+ MB | 中 | 不可逆 |
| **合计** | **~257 MB** | | |

> [!CAUTION]
> Git 历史清理（`git gc` 或 `git filter-branch`）是不可逆操作，请在确认不需要历史版本后再执行。如果项目有远程仓库，需同步更新。

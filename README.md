# 数控刀补量程台

操作员在量程台设定刀补闭区间上下限（默认 **[-20, 20]** 微米，含端点）并交单；刀补值只能落在该闭区间内，越界时**表单入口与直打服务入口都退回同一套规则文案**。每次成功交单把当时刀补原文记入履历；事后若改正单据上的数字，履历旧值保持不动，可用履历与单据现值对照验收。后台 worker 用 PostgreSQL 行锁（`select_for_update(skip_locked=True)`）认领待复核记录，按绝对值是否不超过 12 微米给出「合格」或「超差」。

## 规则与履历

- 区间为闭区间：`下限 <= 刀补 <= 上限` 才收单，端点值合法。
- 校验只有 `desk/services.py` 一个来源，HTTP 表单入口与直打服务入口共用，退回文案完全一致。
- 履历（`OffsetHistory`）只追加：交单记 `submit`、改正记 `correct`，均保存当时刀补原文（`offset_text`）。
- 改正单据数字会重置为「待复核」并追加新履历；旧履历不改不删。`GET /api/history` 同时返回单据现值与 `matches_current` 对照结果。
- 复核员可查看区间与履历，但不能改上下限、不能交单/改正。

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Django 5 + django-ninja（ASGI / uvicorn） |
| 前端 | SolidJS + Vite，nginx 反代 `/api` |
| 数据库 | PostgreSQL 16 |
| 鉴权 | JWT（python-jose），令牌存浏览器 localStorage |

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3196 |
| 接口 | http://localhost:8196 |
| PostgreSQL | localhost:54396（库名 `cncoffset`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| machinist | machine123456 | 设区间、交单、改正 |
| auditor | audit123456 | 只读：可看区间、单据与履历 |

## 启动

```bash
docker compose up --build
```

健康检查：`GET http://localhost:8196/api/health` → `{"status":"ok"}`

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/range` | 查看区间与规则文案（两角色均可） |
| PUT | `/api/range` | 设定上下限（仅操作员） |
| POST | `/api/submissions` | 交单：越界 400 退回同一规则文案 |
| PATCH | `/api/submissions/{id}` | 改正刀补：同校验，追加履历、旧履历不动 |
| GET | `/api/history` | 履历区：原文、单据现值、对照结果 |

## 验收

1. machinist 登录进「量程台」，默认区间为 [-20, 20]；区间设置、交单栏、履历区三区齐全。
2. 交刀补 **5** 应收下；交 **30** 应退回，退回说明闭区间规则；直打服务（`POST /api/submissions`）交 30 同样退回且文案一致。端点 -20、20 应收下，-21 应退回。
3. 成功交单后履历区出现一条「交单」记录，刀补原文为交单时数字。
4. 在复核总览对该单「改正」为新数字后：单据现值更新、履历新增「改正」一条，旧的交单履历原文不变，对照列由「一致」变「已改正」。越界改正整体退回，单据与履历均不变。
5. auditor 登录：区间设置为只读、无交单栏、无改正按钮，但可查看区间与履历；直接调 PUT/POST/PATCH 接口返回 403。
6. 种子数据：刀具 T01 合格（刀补 5 µm）、T09 超差（刀补 20 µm），均带交单履历。

## 目录

```text
backend/          Django 工程（config/、desk/、worker.py）
frontend/         SolidJS 单页
docker-compose.yml
```

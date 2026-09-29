# 数控刀补复核台

操作员在**量程台**设定刀补量程上下限（闭区间）并提交刀具编号与刀补微米值。刀补数值只能落在闭区间内，越界时表单入口（HTTP API）与直打服务入口（`desk.services`）按同一套规则退回。每次成功交单把当时刀补原文记进追加式履历；事后改正单据上的数字只改单据本身，履历旧值保持不动，可在履历区并排对照验收。后台 worker 用 PostgreSQL 行锁（`select_for_update(skip_locked=True)`）认领待复核记录，按绝对值是否不超过 12 微米给出「合格」或「超差」。

## 量程规则（单一来源）

- 区间默认 `[-20, 20]` 微米，**闭区间**，边界 `-20`、`20` 都收下。
- 规则与文案只在 `desk/services.py` 定义：表单入口 `POST /api/submissions` 与直打服务 `create_submission()` 共用，越界返回同一句话。
- 每次成功交单在同一事务内追加一条 `OffsetHistory`（刀补原文 + 解析值），模型层禁止 update/delete。
- 改正单据数字（`PATCH /api/submissions/{id}`）过同一套区间校验、重置为待复核，但绝不触碰履历。

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
| machinist | machine123456 | 设区间、交单、改正单据 |
| auditor | audit123456 | 只读：可看区间与履历，不能改上下限、不能交单/改正 |

## 启动

```bash
docker compose up --build
```

健康检查：`GET http://localhost:8196/api/health` → `{"status":"ok"}`

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/range` | 查看量程上下限与规则文案（两个角色都可看） |
| PUT | `/api/range` | 设置上下限（仅操作员；复核员返回 403） |
| POST | `/api/submissions` | 交单；越界返回 400 与统一规则文案 |
| PATCH | `/api/submissions/{id}` | 改正单据数字，重置待复核；履历不动 |
| GET | `/api/history` | 履历原文与单据当前值对照（`amended` 标记是否已改正） |

## 验收

1. 量程台菜单含区间设置、交单栏、履历区；初始区间为 `-20`～`20`。
2. 交单栏提交 `5`：收下并在履历区出现原文 `5`；提交 `30`：退回，提示「刀补数值只能落在闭区间 [-20, 20] 微米内（含上下限边界）…」，不留单据也不留履历。直打 `desk.services.create_submission(..., "30")` 抛同一文案的 `OffsetOutOfRange`。
3. 在单据详情页把数字改正（如 `5`→`8`）后，履历区该行仍显示旧原文 `5`，单据当前值为 `8`，对照列标「已改正（旧值保留）」。
4. auditor 登录能看区间与履历，但区间为只读，交单栏不可用。

后端测试（本地无 PostgreSQL 时用内存 sqlite）：

```bash
cd backend
PYTHONPATH=. DJANGO_SETTINGS_MODULE=config.settings_test python3 manage.py test desk
```

## 目录

```text
backend/          Django 工程（config/、desk/、worker.py）
frontend/         SolidJS 单页
docker-compose.yml
```

# EA 中央管理系统聊天记录

日期：2026-05-08

## 1. 初始需求

你想做一个 EA 中央管理系统，核心能力包括：实时监控 EA 交易信息、监控 EA 运行情况、给 EA 下达暂停交易、开启交易、平仓、建仓等指令。

我们确定的总体架构是：

```text
MT4/MT5 EA -> 中央 API 服务 -> PostgreSQL/Redis -> Web 管理后台
```

第一版建议采用 HTTP 轮询，先实现：

```text
POST /api/ea/heartbeat
POST /api/ea/snapshot
GET  /api/ea/commands?ea_id=xxx
POST /api/ea/commands/{command_id}/result
```

## 2. 第一版开发方向

先做最小可运行闭环，不先做复杂后台：

```text
EA 启动 -> 上报心跳 -> 后台显示在线 -> 上报账户和持仓 -> 后台下发指令 -> EA 拉取并执行 -> 回传结果
```

第一阶段优先事项：

1. 定义 EA 与服务器的接口协议。
2. 开发 FastAPI 后端 MVP。
3. 开发 MQL4/MQL5 EA 连接器。
4. 做简单管理后台。

## 3. 服务器配置方案

你使用阿里云服务器，第一版使用一台 ECS 即可：

```text
Ubuntu 22.04/24.04
Docker
Docker Compose
Nginx
PostgreSQL
Redis
FastAPI 后端
```

安全组建议只开放：

```text
22   SSH
80   HTTP
443  HTTPS，后面有域名后再启用
```

不要公网开放：

```text
5432 PostgreSQL
6379 Redis
```

当前没有域名和 HTTPS，所以先使用公网 IP + HTTP 测试。

## 4. 服务器测试结果

你执行了一键测试：

```bash
ea-check http://$(curl -s ifconfig.me)/health
```

测试结果核心内容：

```text
[PASS] docker installed
[PASS] nginx installed
[PASS] curl installed
[PASS] docker service is running
[PASS] nginx service is running
[PASS] nginx config is valid
[PASS] ea-backend is running
[PASS] ea-postgres is running
[PASS] ea-redis is running
[PASS] http://47.86.170.144/health returns HTTP 200
Response body: {"status":"ok"}
[PASS] postgres is ready
[PASS] postgres query works
[PASS] redis ping returns PONG
```

结论：服务器基础环境已经通过，可以进入后端开发。

## 5. 已生成后端 MVP 项目

项目目录：

```text
C:\Users\Administrator\ea-control-center
```

已生成内容：

```text
backend/
  Dockerfile
  requirements.txt
  app/
    __init__.py
    config.py
    database.py
    main.py
    models.py
    schemas.py
    security.py
    routers/
      __init__.py
      ea.py
      admin.py

scripts/
  api-smoke-test.sh

docker-compose.yml
nginx-ea-control-center.conf
.env.example
.gitignore
README.md
```

## 6. 数据库表设计

第一版包含这些核心表：

- `ea_instances`：EA 实例状态、账号、版本、最近心跳时间、是否允许交易。
- `account_snapshots`：账户资金快照。
- `positions`：当前持仓。
- `commands`：后台下发给 EA 的指令。
- `command_logs`：指令状态变化和执行日志。

指令状态：

```text
pending -> received -> executing -> success / failed / timeout / cancelled
```

支持的指令类型：

```text
pause_trading
resume_trading
close_all
close_symbol
close_ticket
open_order
update_params
```

## 7. 已实现 FastAPI 接口

EA 端接口：

```text
POST /api/ea/heartbeat
POST /api/ea/snapshot
GET  /api/ea/commands?ea_id=test-ea-001
POST /api/ea/commands/{command_id}/result
```

管理端接口：

```text
GET  /api/admin/eas
GET  /api/admin/eas/{ea_id}/positions
POST /api/admin/commands
GET  /api/admin/commands
POST /api/admin/commands/{command_id}/cancel
```

EA 接口鉴权 Header：

```text
X-EA-Token: your_ea_token
```

管理端接口鉴权 Header：

```text
X-Admin-Token: your_admin_token
```

## 8. 部署命令

把 `C:\Users\Administrator\ea-control-center` 上传到服务器：

```text
/opt/ea-control-center
```

服务器上执行：

```bash
cd /opt/ea-control-center
cp .env.example .env
vim .env
docker compose up -d --build
```

注意修改：

```text
POSTGRES_PASSWORD
DATABASE_URL
EA_API_TOKEN
ADMIN_API_TOKEN
```

如果服务器之前已经有 PostgreSQL 数据目录，`POSTGRES_PASSWORD` 要和原来的密码保持一致。

## 9. API 闭环测试

服务器上执行：

```bash
export EA_API_TOKEN="你在.env里设置的EA_API_TOKEN"
export ADMIN_API_TOKEN="你在.env里设置的ADMIN_API_TOKEN"
chmod +x scripts/api-smoke-test.sh
./scripts/api-smoke-test.sh http://47.86.170.144
```

该脚本模拟：

1. EA 上报心跳。
2. EA 上报账户和持仓快照。
3. 管理端查询 EA 列表。
4. 管理端创建暂停交易指令。
5. EA 拉取指令。
6. EA 回传执行成功。
7. 管理端查看指令状态。

## 10. 当前状态和下一步

当前状态：

- 服务器基础配置通过测试。
- 本地已生成后端 MVP 项目。
- 已有数据库模型和 FastAPI 接口代码。
- 已有 Docker Compose 部署配置。
- 已有一键 API smoke test 脚本。

未完成本地运行验证的原因：

- 当前 Windows 本机没有 Python。
- Docker Desktop 没有启动成功。

建议下一步：

1. 将项目上传到阿里云服务器。
2. 在服务器执行 `docker compose up -d --build`。
3. 运行 `scripts/api-smoke-test.sh`。
4. 测试通过后，开始开发 MQL4/MQL5 EA 连接器。
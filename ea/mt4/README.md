# MT4 对接说明（仅接口层）

当前生产与联调以 **MT5** 为主（见 [`../mt5/EAControlConnector.mq5`](../mt5/EAControlConnector.mq5) 与 [`../mt5/README.md`](../mt5/README.md)）。
本目录**不维护**完整 MT4 EA 源码；MT4 侧只需按 **与 MT5 相同的一组 HTTP/JSON 接口** 接入即可。

## 与后端约定的接口（与 MT5 一致）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/ea/heartbeat` | 头：`X-EA-Token`；JSON 里 `terminal` 请填 **`"MT4"`**，其余字段与 MT5 心跳一致 |
| `POST` | `/api/ea/snapshot` | 账户与持仓列表；`positions[]` 中 `ticket` / `symbol` / `side`(buy/sell) 等与 MT5 相同结构 |
| `GET` | `/api/ea/commands?ea_id=...` | 拉取待执行命令 |
| `POST` | `/api/ea/commands/{id}/result` | 上报执行结果 |

鉴权、命令类型、`payload` 示例均以 **MT5 README** 与后台 OpenAPI 为准。

## MT4 实现时注意点（若日后自写脚本或精简 EA）

- 终端需在 **允许 WebRequest** 列表中加入 API 根地址（如 `http://127.0.0.1:8001`）。
- 持仓在 MT4 多为 **未平仓订单**（`OP_BUY` / `OP_SELL`），需映射到与 MT5 相同的 `positions` 数组字段名与语义。
- 休市或无报价时，若用定时器轮询，建议与 MT5 一样用 **`TimeLocal()`** 驱动 `OnTimer`，避免 `TimeCurrent()` 停住。

需要完整可编译示例时，以 MT5 连接器为参照自行裁剪 MQL4 即可。

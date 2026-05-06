# Command Code Adapter — 管理面板设计文档

> 为 CC Adapter 添加可视化管理页面，支持配置编辑、API 测试和 Key 验证
> 日期：2026-05-07

---

## 1. 概述

在已有 FastAPI 应用上增加一个 Web 管理面板，以可视化方式管理适配器的运行配置、测试 API 连通性和验证 API Key。

### 核心功能

| 功能 | 描述 |
|------|------|
| 配置编辑 | 可视化修改 .env 中的 5 项配置（API Key、Base URL、Host、Port、Log Level） |
| Playground | 调式 `POST /v1/chat/completions` 端点，支持 stream / non-stream 模式 |
| 健康检查 | 查看 `/health` 端点状态 |
| Key 验证 | 发轻量请求到 CC API 验证 Key 是否有效 |
| 登录保护 | 密码保护管理页面，密码为空时跳过 |

### 非功能性需求

- i18n 中/英文切换
- 明暗主题切换 (Light/Dark)
- 零构建工具链（纯 HTML/CSS/JS）

---

## 2. 技术选型

| 层 | 选择 |
|----|------|
| 前端 | 纯 HTML + CSS + JS (无框架、无构建工具) |
| 后端 | FastAPI `StaticFiles` + 新增路由 |
| 认证 | 简单密码 + 内存 token (或 HTTP Basic Auth) |
| 配置持久化 | 写入 .env 文件 + 更新运行时 config 对象 |
| i18n | JS 内嵌中英文映射表，localStorage 持久化 |
| 主题 | CSS 变量 `:root` + `[data-theme="dark"]`，localStorage 持久化 |

---

## 3. 项目结构

```
cc_adapter/
├── admin/
│   ├── __init__.py
│   ├── router.py              # /admin/api/* 路由定义
│   └── auth.py                # 认证 middleware
├── static/                    # 前端静态文件
│   ├── admin.html             # 单页应用主页面
│   ├── admin.css              # 样式（含 light/dark 变量）
│   └── admin.js               # JS（API 调用 + i18n + UI）
├── main.py                    # 注册 admin router + static files
├── ...
```

---

## 4. 后端 API

### 4.1 端点列表

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/admin/` | - | 返回 admin.html 静态页面 |
| `POST` | `/admin/api/login` | 否 | 登录，返回 token |
| `GET` | `/admin/api/config` | 是 | 读取当前配置（隐藏 API Key） |
| `PUT` | `/admin/api/config` | 是 | 写入配置到 .env |
| `POST` | `/admin/api/verify-key` | 是 | 验证 CC API Key |
| `GET` | `/admin/api/health` | 是 | 健康检查 + 附加状态信息 |

### 4.2 配置 API

**GET /admin/api/config 响应:**
```json
{
  "cc_api_key": "****",           // 隐藏明文
  "cc_base_url": "https://api.commandcode.ai",
  "host": "0.0.0.0",
  "port": 8080,
  "log_level": "INFO"
}
```

**PUT /admin/api/config 请求:**
```json
{
  "cc_api_key": "new_key",
  "cc_base_url": "https://api.commandcode.ai",
  "host": "0.0.0.0",
  "port": 8081,
  "log_level": "DEBUG"
}
```
- 只提交需要修改的字段（partial update）
- 写入 .env 文件 + 更新运行时 AppConfig + 更新 CommandCodeClient 实例
- 返回新的配置状态

### 4.3 认证

```
CC_ADMIN_PASSWORD=mysecret    # .env 配置，空字符串 = 不启用认证
```

流程：
1. 前端 POST `/admin/api/login` `{ "password": "..." }`
2. 后端校验密码是否正确
3. 成功 → 返回 `{ "token": "<random_hex>" }`
4. 失败 → 返回 401

认证 middleware 拦截 `/admin/api/*`（除 `/admin/api/login` 外），从 `Authorization: Bearer <token>` 头获取 token 并校验。

### 4.4 Key 验证

**POST /admin/api/verify-key 响应:**
- 使用当前配置的 CC_API_KEY 和 CC_BASE_URL，发一个最小请求到 CC API（如 `POST /alpha/generate` 带上最小的 body）
- 成功: `{ "valid": true, "message": "API Key is valid" }`
- 失败: `{ "valid": false, "message": "401 Unauthorized - Invalid API Key" }`

### 4.5 健康检查

**GET /admin/api/health 响应:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "uptime": 3600,
  "cc_api_key_configured": true
}
```

---

## 5. 前端

### 5.1 布局

```
┌──────────────────────────────────────────────────┐
│  Top Bar: Logo | i18n Switch | Theme Switch       │
├────────┬─────────────────────────────────────────┤
│        │                                          │
│  Nav    │  Content Area                            │
│        │                                          │
│ [状态]  │  (Changes based on selected tab)         │
│ 面板    │                                          │
│        │                                          │
│ [配置]  │                                          │
│ 编辑    │                                          │
│        │                                          │
│ [测试]  │                                          │
│ 面板    │                                          │
│        │                                          │
└────────┴──────────────────────────────────────────┘
```

### 5.2 Tab 说明

**Dashboard 页:**
- 服务状态卡片（绿色/红色指示灯 + host:port）
- API Key 状态（已配置/未配置 + Verify 按钮）
- 快速切换到 Config / Playground 的链接

**Configuration 页:**
- 表单模式，每项一个 label + input:
  - CC_API_KEY → password input
  - CC_BASE_URL → text input
  - CC_ADAPTER_HOST → text input
  - CC_ADAPTER_PORT → number input
  - CC_ADAPTER_LOG_LEVEL → select (DEBUG / INFO / WARNING / ERROR)
- Save 按钮 → 保存后显示成功/失败提示
- Cancel 按钮 → 重置为当前值

**Playground 页:**
- 顶部表单行: Model 输入框 + Messages 文本域 + Stream toggle checkbox
- Send 按钮
- Response 区域:
  - stream 模式: 逐行显示 SSE 文本
  - non-stream: 格式化 JSON 显示
- Clear 按钮清空响应

### 5.3 状态提示

- 操作成功/失败在页面顶部以颜色条 (toast) 显示，3 秒后自动消失
- 不弹窗、不干扰操作

### 5.4 i18n

```javascript
const i18n = {
  zh: {
    title: "管理面板",
    config: "配置",
    playground: "测试",
    dashboard: "状态",
    save: "保存",
    cancel: "取消",
    // ...
  },
  en: {
    title: "Admin Panel",
    config: "Configuration",
    playground: "Playground",
    dashboard: "Dashboard",
    save: "Save",
    cancel: "Cancel",
    // ...
  }
};
```

### 5.5 主题

CSS 变量定义颜色：
```css
:root {
  --bg: #ffffff;
  --bg-secondary: #f5f5f5;
  --text: #1a1a1a;
  --text-secondary: #666;
  --accent: #0066cc;
  --border: #e0e0e0;
  --success: #22c55e;
  --error: #ef4444;
}

[data-theme="dark"] {
  --bg: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --text: #e5e5e5;
  --text-secondary: #999;
  --accent: #3b82f6;
  --border: #404040;
  --success: #22c55e;
  --error: #ef4444;
}
```

---

## 6. 配置热更新

当用户通过管理面板修改配置后，需要同时：

1. 写入 `.env` 文件（保留原有格式和注释）
2. 更新运行时的 `AppConfig` 实例
3. 重新创建 `CommandCodeClient`（如果 API Key 或 Base URL 变了）

流程：
```
PUT /admin/api/config
  → 解析请求 body
  → 读取当前 .env 文件
  → 更新匹配行（保留其他行和注释）
  → 写回 .env
  → 更新 config 对象属性
  → 如果 cc_api_key 或 cc_base_url 变了 → 重建 cc_client
  → 返回新配置
```

---

## 7. 测试策略

### 单元测试

- `test_admin_router.py`:
  - 测试 GET/PUT config 端点
  - 测试 login 成功/失败
  - 测试 auth middleware 拦截未认证请求
  - 测试 verify-key 端点（mock httpx）

### 手动验证

```
# 启动服务
poetry run python -m cc_adapter

# 打开浏览器
open http://localhost:8080/admin/

# 测试场景
1. 配置编辑 → 修改端口 → 刷新页面确认
2. Playground → 发消息 → 看 streaming 输出
3. Key 验证 → 点 Verify → 看结果
4. 切换 i18n → 刷新页面确认持久化
5. 切换主题 → 刷新页面确认持久化
```

---

## 8. 依赖变更

无需新增 Python 依赖。已有 FastAPI + pydantic + httpx 完全覆盖。

---

## 9. 注意事项

1. .env 文件写入要处理并发（目前单用户场景，用简单的 read-write 即可）
2. API Key 在前端始终以 `****` 形式展示，修改时需要重新输入全文
3. 运行时配置热更新不重建整个应用，只替换 client 实例
4. 前端无任何 Node.js 依赖，直接编辑 HTML/CSS/JS 即可开发

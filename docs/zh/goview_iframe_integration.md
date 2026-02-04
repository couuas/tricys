# GoView（纯前端）以 iframe 集成到 tricys_visual 的实现方案

> 目标：在不改动 GoView 源码或最小改动的前提下，将 GoView 作为 tricys_visual 的新板块嵌入，并与现有项目/任务体系联动。

---

## 目录索引

- [GoView（纯前端）以 iframe 集成到 tricys\_visual 的实现方案](#goview纯前端以-iframe-集成到-tricys_visual-的实现方案)
  - [目录索引](#目录索引)
  - [1. 方案概述](#1-方案概述)
  - [2. 组件与系统边界](#2-组件与系统边界)
  - [3. 前端修改方案（tricys\_visual）](#3-前端修改方案tricys_visual)
    - [3.1 目录与文件改动建议](#31-目录与文件改动建议)
    - [3.2 部署 GoView（纯前端）](#32-部署-goview纯前端)
    - [3.3 新增路由](#33-新增路由)
    - [3.4 新增嵌入视图（GoviewView.vue）](#34-新增嵌入视图goviewviewvue)
    - [3.5 UI 统一策略（减少割裂）](#35-ui-统一策略减少割裂)
    - [3.6 鉴权与安全（前端侧）](#36-鉴权与安全前端侧)
  - [4. 后端修改方案（tricys\_backend）](#4-后端修改方案tricys_backend)
    - [4.1 适配接口目标](#41-适配接口目标)
    - [4.2 v1/v2 并行挂载（隔离共存）](#42-v1v2-并行挂载隔离共存)
    - [4.3 v2 路由文件建议路径与目录结构清单](#43-v2-路由文件建议路径与目录结构清单)
    - [4.4 v2 接口清单（GoView 专用）](#44-v2-接口清单goview-专用)
    - [4.5 v2 端点示例代码细节（伪代码）](#45-v2-端点示例代码细节伪代码)
    - [4.6 统一响应格式](#46-统一响应格式)
    - [4.6.1 推荐响应格式（契约示例）](#461-推荐响应格式契约示例)
    - [4.7 适配实现建议](#47-适配实现建议)
    - [4.8 基于现有 API 的真实字段映射](#48-基于现有-api-的真实字段映射)
      - [4.8.1 项目摘要（goview/summary）](#481-项目摘要goviewsummary)
      - [4.8.2 任务列表（goview/tasks）](#482-任务列表goviewtasks)
      - [4.8.3 标量指标（goview/metrics）](#483-标量指标goviewmetrics)
      - [4.8.4 时间序列（goview/timeseries / batch）](#484-时间序列goviewtimeseries--batch)
      - [4.8.5 鉴权与请求头映射](#485-鉴权与请求头映射)
      - [4.8.6 任务结果文件列表映射（文件树/下载）](#486-任务结果文件列表映射文件树下载)
      - [4.8.7 分析任务映射（analysis）](#487-分析任务映射analysis)
  - [5. postMessage 协议约定（宿主 ↔ GoView）](#5-postmessage-协议约定宿主--goview)
    - [5.1 基本约定](#51-基本约定)
    - [5.2 宿主 → GoView](#52-宿主--goview)
    - [5.3 GoView → 宿主](#53-goview--宿主)
  - [7. 技术难点与应对](#7-技术难点与应对)
  - [6. GoView 核心功能与 tricys HDF5 结果适配](#6-goview-核心功能与-tricys-hdf5-结果适配)
    - [6.1 GoView 核心功能（与本项目相关）](#61-goview-核心功能与本项目相关)
    - [6.2 基于 tricys HDF5 的适配功能](#62-基于-tricys-hdf5-的适配功能)
  - [6.3 GoView 组件级配置清单（示例）](#63-goview-组件级配置清单示例)
    - [A. 指标卡（数值卡 / KPI）](#a-指标卡数值卡--kpi)
    - [B. 折线图（单变量）](#b-折线图单变量)
    - [C. 多折线图（多变量）](#c-多折线图多变量)
    - [D. 任务表格（任务清单）](#d-任务表格任务清单)
    - [E. 运行状态卡（最新任务状态）](#e-运行状态卡最新任务状态)
    - [F. 文件树与下载入口](#f-文件树与下载入口)
  - [6.4 GoView 组件如何解析响应（示例）](#64-goview-组件如何解析响应示例)
    - [6.4.1 使用 dataPath（取单一字段）](#641-使用-datapath取单一字段)
    - [6.4.2 使用 transform（组装图表数据）](#642-使用-transform组装图表数据)
    - [6.4.3 解析批量序列](#643-解析批量序列)
  - [8. 可选增强](#8-可选增强)
  - [9. 结论](#9-结论)

---

## 1. 方案概述

- **集成方式**：iframe
- **原因**：最低耦合、最小改造、可快速上线，避免路由与样式冲突。
- **关键要点**：
  - GoView 独立部署为静态站点
  - tricys_visual 新增路由与视图，统一外壳样式
  - 通过 URL 参数或 `postMessage` 传递上下文（projectId、token、数据源地址）
  - 使用后端代理或 CORS 保证数据可访问

---

## 2. 组件与系统边界

**tricys_visual（宿主）**
- 负责：路由入口、统一 UI 外壳、鉴权 token 管理、项目上下文（projectId）
- 输出：token、projectId、API 基址

**GoView（被嵌入）**
- 负责：大屏配置与渲染
- 输入：数据源 URL 与鉴权 token

**tricys_backend（数据源）**
- 负责：提供项目/任务/结果/分析等数据接口
- 输出：可用于 GoView 数据源的统一 JSON

---

## 3. 前端修改方案（tricys_visual）

### 3.1 目录与文件改动建议
- 新增页面：`src/views/GoviewView.vue`
- 新增路由：`/goview`
- 侧边栏入口：`AppSidebar` 中新增“GoView”按钮

### 3.2 部署 GoView（纯前端）
> 目标：不使用域名，直接 `localhost:端口` 访问。

**步骤（本地克隆与运行）**
1) 在当前项目根目录并列克隆 GoView（建议放在 `tricys` 同级目录）：
```
git clone https://gitee.com/dromara/go-view.git
```

2) 进入 GoView 目录并切换纯前端分支：
```
cd go-view
git checkout master
```

3) 安装依赖（推荐 pnpm）：
```
pnpm install
```
如无 pnpm，可使用：
```
npm install
```

4) 本地开发运行（默认端口一般为 3000/5173，以实际输出为准）：
```
pnpm dev
```

5) 访问地址（示例）：
- `http://localhost:5173/`

**在 tricys_visual 中的配置建议**
- 设置 `VITE_GOVIEW_URL` 为 `http://localhost:5173/`
- iframe 加载该地址即可

> 注意：若端口不一致，以 dev server 输出为准。

### 3.3 新增路由

目标文件：`tricys_visual/src/router/index.js`

在 WorkbenchLayout 的子路由中新增一项：

```js
{
  path: 'goview',
  name: 'goview',
  component: () => import('../views/GoviewView.vue')
}
```

如果需要登录限制，可加：

```js
meta: { requiresAuth: true }
```

### 3.4 新增嵌入视图（GoviewView.vue）

功能：
- 统一外壳背景
- 载入 iframe
- 注入项目上下文（projectId、token）

**上下文传递建议**：
1. URL Query
   - `https://your-domain.com/goview/?projectId=xxx&token=yyy&apiBase=zzz`
2. postMessage
   - 宿主发送：
     ```js
     iframeEl.contentWindow.postMessage({
       type: 'TRICYS_CTX',
       projectId,
       token,
       apiBase
     }, goviewOrigin);
     ```
   - GoView 接收：监听 `message` 并写入本地状态或存储。

**建议结构（示例）**

```vue
<template>
  <div class="goview-embed">
    <div class="goview-frame">
      <iframe
        ref="iframeRef"
        :src="iframeSrc"
        class="goview-iframe"
        frameborder="0"
        allowfullscreen
      ></iframe>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();
const iframeRef = ref(null);

const projectId = computed(() => route.query.projectId || localStorage.getItem('tricys_last_pid'));
const token = localStorage.getItem('tricys_auth_token');
const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const goviewBase = import.meta.env.VITE_GOVIEW_URL || 'https://your-domain.com/goview/';

const iframeSrc = computed(() => {
  const url = new URL(goviewBase);
  if (projectId.value) url.searchParams.set('projectId', projectId.value);
  if (token) url.searchParams.set('token', token);
  url.searchParams.set('apiBase', apiBase);
  return url.toString();
});

onMounted(() => {
  // 可选：postMessage 方式（优先）
  const targetOrigin = new URL(goviewBase).origin;
  iframeRef.value?.contentWindow?.postMessage({
    type: 'TRICYS_CTX',
    projectId: projectId.value,
    token,
    apiBase
  }, targetOrigin);
});
</script>

<style scoped>
.goview-embed { width: 100%; height: 100%; background: #05070a; }
.goview-frame { width: 100%; height: 100%; border: 1px solid #1f2a36; box-shadow: 0 0 20px rgba(0,0,0,0.4); }
.goview-iframe { width: 100%; height: 100%; }
</style>
```

说明：
- 使用 `VITE_GOVIEW_URL` 作为 GoView 部署地址
- URL Query 与 postMessage 二选一（推荐 postMessage）
- 统一背景与边框以贴合现有 UI 风格

### 3.5 UI 统一策略（减少割裂）

- 使用宿主页面的 Header/Sidebar
- iframe 外层容器使用统一背景色和边框
- 添加加载态与过渡动画
- 若 GoView 提供暗色主题，则切换为暗色

**侧边栏入口（不改代码，仅记录）**

目标文件：`tricys_visual/src/components/AppSidebar.vue`

在顶部导航组新增一个入口按钮：

```vue
<div
  class="sidebar-item"
  :class="{ active: currentRouteName === 'goview' }"
  @click="navigateTo('goview')"
  title="GoView"
>
  <span class="icon">🧭</span>
  <span class="label-mini">GOV</span>
</div>
```

说明：
- 使用现有 `navigateTo`，保证带上 `projectId`
- 图标与字母缩写可根据风格微调

### 3.6 鉴权与安全（前端侧）

- tricys_visual 已使用 `tricys_auth_token`
- 建议 iframe 加载时注入 token（URL 或 `postMessage`）
- GoView 内部请求带 `Authorization: Bearer <token>`
- 跨域时需限定 `postMessage` 的 `origin`

---

## 4. 后端修改方案（tricys_backend）

### 4.1 适配接口目标

纯前端 GoView 可以配置 REST 数据源，但需要统一返回格式。
建议新增 **GoView 适配接口**，并与 v1 业务隔离。

### 4.2 v1/v2 并行挂载（隔离共存）

目标：原业务继续使用 `/api/v1`，GoView 专用接口使用 `/api/v2/goview/*`。

**后端路由组织（建议）**
- `/api/v1/*`：保持现有业务接口不变
- `/api/v2/goview/*`：新增 GoView 适配接口

**实现要点**
- 新增 `api_v2_router`，仅挂载 GoView 相关 endpoints
- 在主应用中并行 `include_router(api_v1_router, prefix="/api/v1")` 与 `include_router(api_v2_router, prefix="/api/v2")`
- 鉴权、CORS、中间件可复用，不需重复配置

**前端配置**
- GoView 使用 `VITE_API_URL` 指向 `/api/v2`
- tricys_visual 保持 `/api/v1` 不变

**兼容策略**
- 新增字段或变更只发生在 v2
- 若 v2 成熟后，可逐步迁移

### 4.3 v2 路由文件建议路径与目录结构清单

建议新增以下目录结构（与现有 v1 结构保持一致）：

```
tricys_backend/
  api/
    v2/
      __init__.py
      api.py
      endpoints/
        __init__.py
        goview.py
```

建议文件职责：
- `api/v2/api.py`：定义 v2 的顶层路由挂载（只挂载 GoView）
- `api/v2/endpoints/goview.py`：实现 `/goview/*` 适配接口

**挂载示例（伪结构）**
```
# tricys_backend/api/v2/api.py
from fastapi import APIRouter
from tricys_backend.api.v2.endpoints import goview

api_v2_router = APIRouter()
api_v2_router.include_router(goview.router, prefix="/goview", tags=["GoView"])
```

```
# tricys_backend/main.py
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_v2_router, prefix="/api/v2")
```

### 4.4 v2 接口清单（GoView 专用）

**1) 项目摘要**
```
GET /api/v2/goview/summary?projectId=xxx
```

**2) 任务列表（最近 N 条）**
```
GET /api/v2/goview/tasks?projectId=xxx&limit=10
```

**3) 标量指标汇总**
```
GET /api/v2/goview/metrics?taskId=xxx
```

**4) 时间序列（单变量）**
```
GET /api/v2/goview/timeseries?taskId=xxx&var=sds.I
```

**5) 时间序列（批量）**
```
POST /api/v2/goview/timeseries/batch
```

**6) 文件树**
```
GET /api/v2/goview/files?taskId=xxx
```

**7) 文件下载**
```
GET /api/v2/goview/files/download?taskId=xxx&path=...
```

**8) 分析任务列表**
```
GET /api/v2/goview/analysis/tasks?projectId=xxx
```

**9) 分析报告**
```
GET /api/v2/goview/analysis/report?taskId=xxx
```

### 4.5 v2 端点示例代码细节（伪代码）

> 仅展示结构与复用路径，具体异常处理/日志/缓存按需补充。

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Dict, Any, List
from sqlmodel import Session

from tricys_backend.utils.db import get_session
from tricys_backend.api.deps import get_current_user
from tricys_backend.models.user import User
from tricys_backend.services.hdf5_service import HDF5ReaderService
from tricys_backend.services.file_browser_service import FileBrowserService

router = APIRouter()
file_browser = FileBrowserService()
hdf5_service = HDF5ReaderService()

@router.get("/summary")
def goview_summary(projectId: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 project 与 tasks 信息（详见 4.8.1 映射）
    return {"code": 0, "message": "ok", "data": {/*...*/}}

@router.get("/tasks")
def goview_tasks(projectId: str, limit: int = 10, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    return {"code": 0, "message": "ok", "data": [/*...*/]}

@router.get("/metrics")
def goview_metrics(taskId: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 /tasks/{task_id}/result_summary
    return {"code": 0, "message": "ok", "data": {/*...*/}}

@router.get("/timeseries")
def goview_timeseries(taskId: str, var: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 /tasks/{task_id}/results/query
    return {"code": 0, "message": "ok", "data": {"time": [], "value": []}}

@router.post("/timeseries/batch")
def goview_timeseries_batch(payload: Dict[str, Any] = Body(...), session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    return {"code": 0, "message": "ok", "data": {"time": [], "series": {}}}

@router.get("/files")
def goview_files(taskId: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 /tasks/{task_id}/files
    return {"code": 0, "message": "ok", "data": file_browser.list_files(/*workspace_path*/)}

@router.get("/files/download")
def goview_files_download(taskId: str, path: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 /tasks/{task_id}/files/download
    return /* FileResponse */

@router.get("/analysis/tasks")
def goview_analysis_tasks(projectId: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 /analysis/tasks?project_id=...
    return {"code": 0, "message": "ok", "data": [/*...*/]}

@router.get("/analysis/report")
def goview_analysis_report(taskId: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # 复用 /analysis/tasks/{task_id}/report
    return {"code": 0, "message": "ok", "data": {"content": "..."}}
```

### 4.6 统一响应格式

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

**字段约定**
- `code`：0 表示成功，非 0 表示错误
- `message`：错误或提示信息
- `data`：业务数据
- 可选扩展：`meta`（分页/版本信息）

---

### 4.6.1 推荐响应格式（契约示例）

**通用响应**
```json
{
  "code": 0,
  "message": "ok",
  "data": { "time": [0,1], "value": [1.0, 1.2] }
}
```

**错误响应**
```json
{
  "code": 10001,
  "message": "Task not found",
  "data": null
}
```

### 4.7 适配实现建议

- 基于现有接口二次封装：
  - `/tasks/{task_id}/result_summary`
  - `/tasks/{task_id}/results/query`
- 对结果统一抽象成 GoView “数据源返回结构”
- 兼容 GoView 组件配置中的 `dataHandler`（若启用前端数据处理）

### 4.8 基于现有 API 的真实字段映射

> 说明：以下映射基于当前后端接口返回结构与前端已使用字段，避免引入不存在的字段。

#### 4.8.1 项目摘要（goview/summary）

**数据来源**
- 项目详情：`GET /api/v1/project/{project_id}`
- 项目列表（含更新时间）：`GET /api/v1/project/`
- 任务列表（推断项目状态）：`GET /api/v1/tasks?limit=1&offset=0`

**字段映射**
- `projectName` ← 项目详情 `name`
- `lastUpdated` ← 项目列表 `updated_at`（若空则使用 `created_at`）
- `status` ← 最近任务 `status`（若无任务则置为 `NO_TASK`）

**映射示例（伪结构）**
```json
{
  "projectName": "project.name",
  "lastUpdated": "project_list[project_id].updated_at || created_at",
  "status": "latest_task.status || NO_TASK"
}
```

#### 4.8.2 任务列表（goview/tasks）

**数据来源**
- 任务列表：`GET /api/v1/tasks?limit=N&offset=0`

**字段映射**
- `id` ← `task.id`
- `name` ← `task.name`
- `status` ← `task.status`
- `createdAt` ← `task.created_at`
- `updatedAt` ← `task.updated_at`
- `type` ← `task.type`（若存在；无则忽略）

**映射示例（伪结构）**
```json
{
  "id": "task.id",
  "name": "task.name",
  "status": "task.status",
  "createdAt": "task.created_at",
  "updatedAt": "task.updated_at",
  "type": "task.type (optional)"
}
```

#### 4.8.3 标量指标（goview/metrics）

**数据来源**
- 结果摘要：`GET /api/v1/tasks/{task_id}/result_summary`

**字段映射**
- `metrics` ← 返回体中的 `metrics`

**映射示例（伪结构）**
```json
{
  "TBR": "result_summary.metrics.TBR",
  "TotalInventory": "result_summary.metrics.TotalInventory"
}
```

#### 4.8.4 时间序列（goview/timeseries / batch）

**数据来源**
- 结果查询：`POST /api/v1/tasks/{task_id}/results/query`

**字段映射**
- `time` ← `query_results.time`
- `value` ← `query_results[variable]`

**单变量映射示例（伪结构）**
```json
{
  "time": "query_results.time",
  "value": "query_results['sds.I']"
}
```

**多变量映射示例（伪结构）**
```json
{
  "time": "query_results.time",
  "series": {
    "sds.I": "query_results['sds.I']",
    "wds.T": "query_results['wds.T']"
  }
}
```

#### 4.8.5 鉴权与请求头映射

- tricys_visual token：`localStorage['tricys_auth_token']`
- 传递方式：`Authorization: Bearer <token>`

**示例**
```
Authorization: Bearer ${token}
```

#### 4.8.6 任务结果文件列表映射（文件树/下载）

**数据来源**
- 文件列表：`GET /api/v1/tasks/{task_id}/files`
- 文件下载：`GET /api/v1/tasks/{task_id}/files/download?path=...`

**字段映射**
- 列表接口返回为文件树数组（后端 `FileBrowserService.list_files`）
- 典型字段（以实际返回为准）：
  - `name`：文件/目录名
  - `path`：相对路径
  - `type`：`file` / `dir`
  - `size`：文件大小（若有）
  - `children`：子节点（目录类型）
  - `modified`：更新时间（若有）

**GoView 侧使用建议**
- 文件浏览组件：直接渲染 `files` 列表
- 文件下载：拼接下载 URL

**映射示例（伪结构）**
```json
{
  "files": "tasks/{task_id}/files"
}
```

**示例响应（文件树）**
```json
[
  {
    "name": "results",
    "path": "results",
    "type": "dir",
    "children": [
      {
        "name": "standard_report.md",
        "path": "results/standard_report.md",
        "type": "file",
        "size": 10240,
        "modified": "2026-02-05T07:30:00Z"
      },
      {
        "name": "plots",
        "path": "results/plots",
        "type": "dir",
        "children": [
          {
            "name": "plot_001.png",
            "path": "results/plots/plot_001.png",
            "type": "file",
            "size": 204800,
            "modified": "2026-02-05T07:31:00Z"
          }
        ]
      }
    ]
  },
  {
    "name": "simulation.log",
    "path": "simulation.log",
    "type": "file",
    "size": 4096,
    "modified": "2026-02-05T07:20:00Z"
  }
]
```

下载示例：
```
GET /api/v1/tasks/{task_id}/files/download?path=<relative_path>
```

**文件树前端渲染策略（建议）**
- 递归渲染 `children` 形成树结构
- 目录节点：展示折叠/展开按钮
- 文件节点：展示文件类型图标 + 大小 + 更新时间
- 点击文件：触发下载或预览
- 大文件（如 .h5 / .csv）：优先下载，避免直接预览导致卡顿
- 建议增加搜索/过滤（按文件名、扩展名）

**文件下载权限控制说明**
- 后端会校验任务归属（project.user_id == current_user.id）
- GoView 请求时必须携带 `Authorization: Bearer <token>`
- 若 iframe 跨域，需确保 token 不泄露，且 `postMessage` 限制 `origin`

#### 4.8.7 分析任务映射（analysis）

**数据来源**
- 分析任务列表：`GET /api/v1/analysis/tasks?project_id=...`
- 单个任务详情：`GET /api/v1/analysis/tasks/{task_id}`
- 报告内容：`GET /api/v1/analysis/tasks/{task_id}/report`

**字段映射**
- `id` ← `task.id`
- `name` ← `task.name`
- `status` ← `task.status`
- `createdAt` ← `task.created_at`
- `updatedAt` ← `task.updated_at`
- `config` ← `task.config_json`
- `report` ← `report.content`（Markdown 字符串）

**映射示例（伪结构）**
```json
{
  "id": "task.id",
  "name": "task.name",
  "status": "task.status",
  "createdAt": "task.created_at",
  "updatedAt": "task.updated_at",
  "config": "task.config_json",
  "report": "report.content"
}
```

---

## 5. postMessage 协议约定（宿主 ↔ GoView）

> 目的：保证 tricys_visual 与 GoView 之间安全、稳定地交换上下文。

### 5.1 基本约定
- **消息方向**：
  - 宿主 → GoView：上下文初始化、项目切换、刷新指令
  - GoView → 宿主：状态同步、错误上报、请求刷新
- **消息格式**（统一结构）：
  ```json
  {
    "type": "TRICYS_CTX",
    "payload": { ... }
  }
  ```
- **安全**：必须校验 `origin`，禁止 `*`。

### 5.2 宿主 → GoView

**1) 初始化上下文**
```json
{
  "type": "TRICYS_CTX",
  "payload": {
    "projectId": "<uuid>",
    "token": "<jwt>",
    "apiBase": "http://localhost:8000/api/v1"
  }
}
```

**2) 项目切换**
```json
{
  "type": "TRICYS_PROJECT_SWITCH",
  "payload": {
    "projectId": "<uuid>"
  }
}
```

**3) 强制刷新**
```json
{
  "type": "TRICYS_REFRESH",
  "payload": {
    "reason": "project-changed"
  }
}
```

### 5.3 GoView → 宿主

**1) 上下文就绪**
```json
{
  "type": "GOVIEW_READY",
  "payload": {
    "version": "x.y.z"
  }
}
```

**2) 错误上报**
```json
{
  "type": "GOVIEW_ERROR",
  "payload": {
    "message": "Data source failed",
    "code": "DATA_FETCH_FAILED"
  }
}
```

**3) 请求宿主刷新数据**
```json
{
  "type": "GOVIEW_REQUEST_REFRESH",
  "payload": {
    "projectId": "<uuid>"
  }
}
```

---

## 7. 技术难点与应对

| 难点 | 风险 | 解决方案 |
|---|---|---|
| 路由冲突 | 页面跳转紊乱 | iframe 隔离路由 |
| 样式污染 | UI 割裂 | 外壳统一 + GoView 暗色主题 |
| 鉴权 | 数据无法访问 | token 注入 + 请求代理 |
| 跨域 | 请求被阻止 | 同域部署或 CORS |
| 数据格式 | GoView 无法解析 | 后端适配接口 |
| 消息联动 | 项目切换无响应 | `postMessage` 协议 |

---

## 6. GoView 核心功能与 tricys HDF5 结果适配

### 6.1 GoView 核心功能（与本项目相关）
- 大屏布局与组件化可视化（图表、指标卡、表格、文本、图片）
- 数据源接入（HTTP / 定时刷新 / 自定义处理）
- 主题与样式配置（暗色主题、组件样式、布局）
- 多模块编排与联动

### 6.2 基于 tricys HDF5 的适配功能

**1) 指标卡（KPI）**
- 数据来源：`/api/v2/goview/metrics?taskId=...`
- 适配内容：`TBR`、`TotalInventory`、`WallLoad` 等标量指标

**2) 时间序列折线图**
- 数据来源：`/api/v2/goview/timeseries?taskId=...&var=...`
- 适配内容：关键变量随时间变化

**3) 多变量对比图**
- 数据来源：`/api/v2/goview/timeseries/batch`
- 适配内容：同一时间轴下多个变量曲线

**4) 参数扫掠对比图**
- 数据来源：`/api/v2/goview/timeseries/batch`（按 `job_id` 分组）
- 适配内容：不同参数组合的结果对比

**5) 任务与指标表格**
- 数据来源：`/api/v2/goview/tasks` + `/api/v2/goview/metrics`
- 适配内容：任务列表、状态与核心指标汇总

**6) 结果文件与报告入口**
- 数据来源：`/api/v2/goview/files` + `/api/v2/goview/analysis/report`
- 适配内容：文件树展示、报告链接与下载

**7) 运行状态与监控面板**
- 数据来源：`/api/v2/goview/summary` + `/api/v2/goview/tasks`
- 适配内容：最新任务状态、更新时间、运行统计

---

## 6.3 GoView 组件级配置清单（示例）

> 以下为组件级别的配置建议，字段为“伪结构”，实际以 GoView 组件配置面板为准。

### A. 指标卡（数值卡 / KPI）

**适用组件**：数字卡、指标卡

**数据源**：`/api/v2/goview/metrics?taskId=...`

**示例配置**
```json
{
  "type": "http",
  "url": "${apiBase}/goview/metrics?taskId=${taskId}",
  "method": "GET",
  "headers": { "Authorization": "Bearer ${token}" },
  "dataPath": "data.TBR"
}
```

### B. 折线图（单变量）

**适用组件**：折线图

**数据源**：`/api/v2/goview/timeseries?taskId=...&var=sds.I`

**示例配置**
```json
{
  "type": "http",
  "url": "${apiBase}/goview/timeseries?taskId=${taskId}&var=sds.I",
  "method": "GET",
  "headers": { "Authorization": "Bearer ${token}" },
  "transform": "(resp) => ({ x: resp.data.time, y: resp.data.value })"
}
```

### C. 多折线图（多变量）

**适用组件**：多折线图 / 复合折线图

**数据源**：`/api/v2/goview/timeseries/batch`

**示例配置**
```json
{
  "type": "http",
  "url": "${apiBase}/goview/timeseries/batch",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer ${token}"
  },
  "body": {
    "taskId": "${taskId}",
    "variables": ["sds.I", "wds.T"]
  },
  "transform": "(resp) => ({ time: resp.data.time, series: resp.data.series })"
}
```

### D. 任务表格（任务清单）

**适用组件**：表格 / 列表

**数据源**：`/api/v2/goview/tasks?projectId=...&limit=10`

**示例配置**
```json
{
  "type": "http",
  "url": "${apiBase}/goview/tasks?projectId=${projectId}&limit=10",
  "method": "GET",
  "headers": { "Authorization": "Bearer ${token}" },
  "dataPath": "data"
}
```

### E. 运行状态卡（最新任务状态）

**适用组件**：文本 / 状态卡

**数据源**：`/api/v2/goview/summary?projectId=...`

**示例配置**
```json
{
  "type": "http",
  "url": "${apiBase}/goview/summary?projectId=${projectId}",
  "method": "GET",
  "headers": { "Authorization": "Bearer ${token}" },
  "dataPath": "data.status"
}
```

### F. 文件树与下载入口

**适用组件**：文件列表 / 目录树（自定义组件或表格）

**数据源**：`/api/v2/goview/files?taskId=...`

**示例配置**
```json
{
  "type": "http",
  "url": "${apiBase}/goview/files?taskId=${taskId}",
  "method": "GET",
  "headers": { "Authorization": "Bearer ${token}" },
  "dataPath": "data"
}
```

**下载链接模板**
```
${apiBase}/goview/files/download?taskId=${taskId}&path=${path}
```

---

## 6.4 GoView 组件如何解析响应（示例）

> 通过 `dataPath` 或 `transform` 明确解析规则，保证前后端契约清晰。

### 6.4.1 使用 dataPath（取单一字段）

**响应格式**
```json
{ "code": 0, "message": "ok", "data": { "TBR": 1.12 } }
```

**组件配置**
```json
{
  "dataPath": "data.TBR"
}
```

### 6.4.2 使用 transform（组装图表数据）

**响应格式**
```json
{ "code": 0, "message": "ok", "data": { "time": [0,1], "value": [1.0, 1.2] } }
```

**组件配置**
```json
{
  "transform": "(resp) => ({ x: resp.data.time, y: resp.data.value })"
}
```

### 6.4.3 解析批量序列

**响应格式**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "time": [0,1],
    "series": { "sds.I": [1.0, 1.1], "wds.T": [10, 11] }
  }
}
```

**组件配置**
```json
{
  "transform": "(resp) => ({ time: resp.data.time, series: resp.data.series })"
}
```

---

## 8. 可选增强

- 增加 GoView 与项目任务关联（自动切换数据源）
- 增加“从 tricys_visual 直接打开 GoView 大屏”的快捷入口
- 增加访问控制（只允许已登录用户访问 GoView URL）

---

## 9. 结论

iframe 集成是 tricys_visual 与 GoView 纯前端结合的最优解：
- 成本最低
- 风险最小
- 迭代最快

后续如需深度整合，可考虑微前端或源码融合，但维护成本显著增加。

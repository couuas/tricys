# Tricys x GoView 最终集成实现方案（API v2）

本文档合并并整理了 GoView master-fetch 后端兼容方案与 tricys_visual 的 iframe 集成方案，作为最终实施指南。

更新时间：2026-02-09

---

## 目录

- [Tricys x GoView 最终集成实现方案（API v2）](#tricys-x-goview-最终集成实现方案api-v2)
  - [目录](#目录)
  - [1. 目标与决策](#1-目标与决策)
  - [2. 架构总览](#2-架构总览)
  - [3. GoView 编辑器（master-fetch）前端调整](#3-goview-编辑器master-fetch前端调整)
  - [4. tricys\_visual iframe 集成（方案 B）](#4-tricys_visual-iframe-集成方案-b)
  - [5. 后端 API v2 兼容层（master-fetch 必需）](#5-后端-api-v2-兼容层master-fetch-必需)
    - [5.1 路由前缀](#51-路由前缀)
    - [5.2 必需接口（master-fetch）](#52-必需接口master-fetch)
    - [5.3 响应契约](#53-响应契约)
    - [5.4 登录复用](#54-登录复用)
    - [5.5 数据模型建议](#55-数据模型建议)
  - [6. GoView 图表数据适配接口（可选）](#6-goview-图表数据适配接口可选)
  - [7. 字段映射与响应契约](#7-字段映射与响应契约)
  - [8. postMessage 协议约定](#8-postmessage-协议约定)
  - [9. GoView 组件配置示例（tricys 数据适配）](#9-goview-组件配置示例tricys-数据适配)
  - [10. 接口请求/响应示例（更细）](#10-接口请求响应示例更细)
    - [10.1 sys/login](#101-syslogin)
    - [10.2 project/create](#102-projectcreate)
    - [10.3 project/save/data](#103-projectsavedata)
    - [10.4 project/getData](#104-projectgetdata)
    - [10.5 project/upload](#105-projectupload)
  - [11. 代码级伪实现模板](#11-代码级伪实现模板)
    - [11.1 路由挂载（v2）](#111-路由挂载v2)
    - [11.2 统一响应封装](#112-统一响应封装)
    - [11.3 登录适配](#113-登录适配)
    - [11.4 getData 白名单逻辑](#114-getdata-白名单逻辑)
    - [11.5 SQLModel 定义草案](#115-sqlmodel-定义草案)
    - [11.6 路由文件模板（goview/router.py）](#116-路由文件模板goviewrouterpy)
    - [11.7 project.py 伪实现（含校验、分页、上传）](#117-projectpy-伪实现含校验分页上传)
    - [11.8 sys.py 伪实现（含 JSON/form 兼容）](#118-syspy-伪实现含-jsonform-兼容)
    - [11.9 deps.py 伪实现（token 解析/白名单）](#119-depspy-伪实现token-解析白名单)
    - [11.10 deps.py 中间件与异常处理（完整示例）](#1110-depspy-中间件与异常处理完整示例)
    - [11.11 responses.py 伪实现（统一响应）](#1111-responsespy-伪实现统一响应)
    - [11.12 file save 伪实现（上传保存）](#1112-file-save-伪实现上传保存)
    - [11.13 project.py 分页返回 meta 结构](#1113-projectpy-分页返回-meta-结构)
    - [11.14 上传文件类型/大小白名单策略](#1114-上传文件类型大小白名单策略)
  - [12. 错误码、白名单与安全要点](#12-错误码白名单与安全要点)
  - [13. 实施步骤（最小改动集）](#13-实施步骤最小改动集)
  - [14. 测试与验证](#14-测试与验证)
  - [15. 文件改动清单](#15-文件改动清单)
  - [16. 参考资料](#16-参考资料)

---

## 1. 目标与决策

- 采用 GoView master-fetch 以支持编辑与发布。
- 后端兼容层使用 /api/v2/goview。
- tricys_visual 使用 iframe 方案 B（apiBase 含完整 /api/v2/goview 前缀）。
- 登录兼容 JSON 与 form，复用现有登录逻辑。

---

## 2. 架构总览

- tricys_goview（GoView master-fetch）：项目 CRUD、发布、资源上传。
- tricys_visual：iframe 嵌入 GoView，通过 postMessage 传递上下文。
- tricys_backend：对外暴露 /api/v2/goview 兼容接口。
- 可选：增加 tricys HDF5 数据适配接口供图表使用。

---

## 3. GoView 编辑器（master-fetch）前端调整

- 请求前缀：
  - tricys_goview/src/settings/httpSetting.ts
  - axiosPre = "/api/v2/goview"
- baseURL：
  - tricys_goview/src/api/axios.ts 使用 (prod ? VITE_PRO_PATH : "") + axiosPre
- 环境变量：
  - tricys_goview/.env
  - VITE_DEV_PATH / VITE_PRO_PATH 指向后端主机

---

## 4. tricys_visual iframe 集成（方案 B）

- GoviewView 传入 apiBase：
  - apiBase = http://<host>/api/v2/goview
- 环境变量示例（tricys_visual/.env）：
  - VITE_GOVIEW_URL = http://localhost:5173/
  - VITE_API_V2_URL = http://localhost:8000/api/v2/goview
  - VITE_API_URL = http://localhost:8000/api/v1
- postMessage：
  - type: TRICYS_CTX
  - payload: projectId, token, apiBase

说明：只要 GoView 能访问后端主机，iframe 集成不受影响。

---

## 5. 后端 API v2 兼容层（master-fetch 必需）

### 5.1 路由前缀

- /api/v2/goview

### 5.2 必需接口（master-fetch）

系统接口（sys）：
- POST /api/v2/goview/sys/login
- GET /api/v2/goview/sys/logout
- GET /api/v2/goview/sys/getOssInfo

项目接口（project）：
- GET /api/v2/goview/project/list
- POST /api/v2/goview/project/create
- GET /api/v2/goview/project/getData
- POST /api/v2/goview/project/save/data
- POST /api/v2/goview/project/edit
- DELETE /api/v2/goview/project/delete
- PUT /api/v2/goview/project/publish
- POST /api/v2/goview/project/upload

### 5.3 响应契约

- 成功：{ code: 200, msg: "success", data: ... }
- 失败：{ code: <err>, msg: <message>, data: null }
- token 失效：code = 886

### 5.4 登录复用

- 复用 verify_password + create_access_token。
- 兼容 JSON 与 form。
- 返回 tokenName 与 tokenValue 供前端注入 header。

### 5.5 数据模型建议

新增 GoviewProject，字段建议：
- id (uuid)
- projectName
- content (string)
- state (-1/1)
- indexImage
- remarks
- createUserId
- createTime

---

## 6. GoView 图表数据适配接口（可选）

用于 GoView 图表直接消费 tricys 数据：

- GET /api/v2/goview/summary?projectId=...
- GET /api/v2/goview/tasks?projectId=...&limit=10
- GET /api/v2/goview/metrics?taskId=...
- GET /api/v2/goview/timeseries?taskId=...&var=...
- POST /api/v2/goview/timeseries/batch
- GET /api/v2/goview/files?taskId=...
- GET /api/v2/goview/files/download?taskId=...&path=...
- GET /api/v2/goview/analysis/tasks?projectId=...
- GET /api/v2/goview/analysis/report?taskId=...

建议采用 { code, msg, data } 格式以保持一致。

---

## 7. 字段映射与响应契约

ProjectItem：
- id
- projectName
- state
- createTime
- indexImage
- createUserId
- remarks

ProjectDetail 额外字段：
- content (string)

登录响应：
- token: { tokenValue, tokenName }
- userinfo: { nickname, username, id }

接口参数细化：
- sys/login: JSON or form (username, password)
- project/list: page, pageSize, keyword
- project/create: projectName, remarks, indexImage, state
- project/getData: id
- project/save/data: id, content (x-www-form-urlencoded)
- project/edit: id, projectName, remarks, indexImage
- project/delete: id
- project/publish: id, state
- project/upload: file (multipart/form-data)

---

## 8. postMessage 协议约定

消息结构：
{
  "type": "TRICYS_CTX",
  "payload": { ... }
}

宿主 -> GoView：
- TRICYS_CTX: projectId, token, apiBase
- TRICYS_PROJECT_SWITCH: projectId
- TRICYS_REFRESH: reason

GoView -> 宿主：
- GOVIEW_READY: version
- GOVIEW_ERROR: message, code
- GOVIEW_REQUEST_REFRESH: projectId

安全要求：必须校验 origin，不使用 "*"。

---

## 9. GoView 组件配置示例（tricys 数据适配）

指标卡：
- URL: ${apiBase}/metrics?taskId=${taskId}
- dataPath: data.TBR

单变量折线：
- URL: ${apiBase}/timeseries?taskId=${taskId}&var=sds.I
- transform: (resp) => ({ x: resp.data.time, y: resp.data.value })

多变量折线：
- URL: ${apiBase}/timeseries/batch
- body: { taskId, variables }
- transform: (resp) => ({ time: resp.data.time, series: resp.data.series })

文件树：
- URL: ${apiBase}/files?taskId=${taskId}
- dataPath: data

---

## 10. 接口请求/响应示例（更细）

### 10.1 sys/login

Request (JSON):
```
POST /api/v2/goview/sys/login
{
  "username": "demo",
  "password": "demo"
}
```

Response:
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "token": { "tokenValue": "<jwt>", "tokenName": "token" },
    "userinfo": { "nickname": "demo", "username": "demo", "id": "<uuid>" }
  }
}
```

### 10.2 project/create

Request:
```
POST /api/v2/goview/project/create
{
  "projectName": "Demo Board",
  "remarks": "first draft",
  "indexImage": "",
  "state": -1
}
```

Response:
```
{
  "code": 200,
  "msg": "success",
  "data": { "id": "<uuid>" }
}
```

### 10.3 project/save/data

Request (x-www-form-urlencoded):
```
POST /api/v2/goview/project/save/data
id=<uuid>&content=<json-string>
```

Response:
```
{ "code": 200, "msg": "success", "data": null }
```

### 10.4 project/getData

Request:
```
GET /api/v2/goview/project/getData?id=<uuid>
```

Response:
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "id": "<uuid>",
    "projectName": "Demo Board",
    "state": 1,
    "indexImage": "",
    "createUserId": "<uuid>",
    "createTime": "2026-02-09T10:00:00Z",
    "remarks": "first draft",
    "content": "{...}"
  }
}
```

### 10.5 project/upload

Request (multipart/form-data):
```
POST /api/v2/goview/project/upload
file=@image.png
```

Response:
```
{
  "code": 200,
  "msg": "success",
  "data": { "fileName": "image.png", "fileurl": "/assets/goview/image.png" }
}
```

---

## 11. 代码级伪实现模板

### 11.1 路由挂载（v2）

```python
from fastapi import APIRouter
from tricys_backend.api.v2.goview import router as goview_router

api_v2_router = APIRouter()
api_v2_router.include_router(goview_router, prefix="/goview", tags=["GoView"])
```

### 11.2 统一响应封装

```python
def success(data=None, msg="success"):
    return {"code": 200, "msg": msg, "data": data}

def error(code, msg):
    return {"code": code, "msg": msg, "data": None}
```

### 11.3 登录适配

```python
@router.post("/sys/login")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
  payload = {}
  if request.headers.get("content-type", "").startswith("application/json"):
    payload = await request.json()
  username = payload.get("username") or form.username
  password = payload.get("password") or form.password
  # verify_password + create_access_token
  return success({
    "token": {"tokenValue": token, "tokenName": "token"},
    "userinfo": {"nickname": user.username, "username": user.username, "id": user.id}
  })
```

### 11.4 getData 白名单逻辑

```python
@router.get("/project/getData")
def get_data(id: str, session: Session = Depends(get_session)):
    # 允许匿名，仅返回已发布项目
    project = get_project(session, id)
    if project.state != 1:
        return error(403, "not published")
    return success(project_to_detail(project))
```

### 11.5 SQLModel 定义草案

```python
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlmodel import SQLModel, Field

class GoviewProject(SQLModel, table=True):
  id: str = Field(primary_key=True)
  project_name: str
  content: str
  state: int = -1
  index_image: str = ""
  remarks: str = ""
  create_user_id: str
  create_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
  update_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### 11.6 路由文件模板（goview/router.py）

```python
from fastapi import APIRouter
from tricys_backend.api.v2.goview import sys, project

router = APIRouter()
router.include_router(sys.router, prefix="/sys", tags=["GoView"])
router.include_router(project.router, prefix="/project", tags=["GoView"])
```

### 11.7 project.py 伪实现（含校验、分页、上传）

```python
from fastapi import APIRouter, Depends, UploadFile, File, Query, Form
from sqlmodel import Session, select
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
import uuid

from tricys_backend.utils.db import get_session
from tricys_backend.api.v2.goview.responses import success, error
from tricys_backend.api.v2.goview.deps import require_token, optional_token
from tricys_backend.models.goview_project import GoviewProject

router = APIRouter()

@router.get("/list")
def list_projects(
  page: int = Query(1, ge=1),
  pageSize: int = Query(20, ge=1, le=200),
  keyword: Optional[str] = None,
  session: Session = Depends(get_session),
  user = Depends(require_token)
):
  offset = (page - 1) * pageSize
  query = select(GoviewProject).where(GoviewProject.create_user_id == user.id)
  if keyword:
    query = query.where(GoviewProject.project_name.contains(keyword))
  total = session.exec(select(func.count()).select_from(query.subquery())).one()
  items = session.exec(query.offset(offset).limit(pageSize)).all()
  data = [{
    "id": p.id,
    "projectName": p.project_name,
    "state": p.state,
    "createTime": p.create_time.isoformat(),
    "indexImage": p.index_image,
    "createUserId": p.create_user_id,
    "remarks": p.remarks,
  } for p in items]
  return success(data)

@router.post("/create")
def create_project(payload: dict, session: Session = Depends(get_session), user = Depends(require_token)):
  name = (payload.get("projectName") or "New Project").strip()
  if len(name) > 200:
    return error(400, "projectName too long")
  project = GoviewProject(
    id=str(uuid.uuid4()),
    project_name=name,
    content=payload.get("content") or "{}",
    state=int(payload.get("state", -1)),
    index_image=payload.get("indexImage") or "",
    remarks=payload.get("remarks") or "",
    create_user_id=user.id,
  )
  session.add(project)
  session.commit()
  return success({"id": project.id})

@router.get("/getData")
def get_data(id: str, session: Session = Depends(get_session), user = Depends(optional_token)):
  project = session.get(GoviewProject, id)
  if not project:
    return error(404, "not found")
  if project.state != 1 and (not user or project.create_user_id != user.id):
    return error(403, "not published")
  return success({
    "id": project.id,
    "projectName": project.project_name,
    "state": project.state,
    "indexImage": project.index_image,
    "createUserId": project.create_user_id,
    "createTime": project.create_time.isoformat(),
    "remarks": project.remarks,
    "content": project.content,
  })

@router.post("/save/data")
def save_data(id: str = Form(...), content: str = Form(...), session: Session = Depends(get_session), user = Depends(require_token)):
  project = session.get(GoviewProject, id)
  if not project or project.create_user_id != user.id:
    return error(403, "forbidden")
  project.content = content
  project.update_time = datetime.now(timezone.utc)
  session.add(project)
  session.commit()
  return success(None)

@router.post("/edit")
def edit_project(payload: dict, session: Session = Depends(get_session), user = Depends(require_token)):
  project = session.get(GoviewProject, payload.get("id"))
  if not project or project.create_user_id != user.id:
    return error(403, "forbidden")
  if "projectName" in payload:
    name = payload.get("projectName") or ""
    if len(name) > 200:
      return error(400, "projectName too long")
    project.project_name = name
  if "remarks" in payload:
    project.remarks = payload.get("remarks") or ""
  if "indexImage" in payload:
    project.index_image = payload.get("indexImage") or ""
  project.update_time = datetime.now(timezone.utc)
  session.add(project)
  session.commit()
  return success(None)

@router.delete("/delete")
def delete_project(id: str, session: Session = Depends(get_session), user = Depends(require_token)):
  project = session.get(GoviewProject, id)
  if not project or project.create_user_id != user.id:
    return error(403, "forbidden")
  session.delete(project)
  session.commit()
  return success(None)

@router.put("/publish")
def publish_project(payload: dict, session: Session = Depends(get_session), user = Depends(require_token)):
  project = session.get(GoviewProject, payload.get("id"))
  if not project or project.create_user_id != user.id:
    return error(403, "forbidden")
  project.state = int(payload.get("state", -1))
  project.update_time = datetime.now(timezone.utc)
  session.add(project)
  session.commit()
  return success(None)

@router.post("/upload")
def upload_file(file: UploadFile = File(...), user = Depends(require_token)):
  # validate file type/size here
  filename = file.filename or "upload.bin"
  save_path = save_to_assets(file)  # implement file save
  safe_name = Path(save_path).name
  return success({"fileName": filename, "fileurl": f"/assets/goview/{safe_name}"})
```

### 11.8 sys.py 伪实现（含 JSON/form 兼容）

```python
from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from tricys_backend.utils.db import get_session
from tricys_backend.core.security import verify_password, create_access_token
from tricys_backend.models.user import User
from tricys_backend.api.v2.goview.responses import success, error

router = APIRouter()

@router.post("/login")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
  payload = {}
  if request.headers.get("content-type", "").startswith("application/json"):
    payload = await request.json()
  username = payload.get("username") or form.username
  password = payload.get("password") or form.password
  user = session.exec(select(User).where(User.username == username)).first()
  if not user or not verify_password(password, user.hashed_password):
    return error(400, "invalid credentials")
  token = create_access_token(user.id)
  return success({
    "token": {"tokenValue": token, "tokenName": "token"},
    "userinfo": {"nickname": user.username, "username": user.username, "id": user.id}
  })

@router.get("/logout")
def logout():
  return success(None)

@router.get("/getOssInfo")
def get_oss_info():
  return success({"bucketURL": "/api/v2/goview/project/upload"})
```

### 11.9 deps.py 伪实现（token 解析/白名单）

```python
from fastapi import Request, HTTPException, Depends
from typing import Optional
from fastapi.responses import JSONResponse

from tricys_backend.api.v2.goview.responses import error
from tricys_backend.core.security import decode_access_token
from tricys_backend.utils.db import get_session
from tricys_backend.models.user import User

ALLOW_LIST = {
  ("GET", "/project/getData"),
  ("GET", "/sys/getOssInfo"),
  ("POST", "/sys/login"),
}

def is_allowed(method: str, path: str) -> bool:
  return (method.upper(), path) in ALLOW_LIST

def extract_token(request: Request) -> Optional[str]:
  token = request.headers.get("token")
  if not token:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
      token = auth.replace("Bearer ", "", 1)
  return token

def require_token(request: Request, session = Depends(get_session)):
  if is_allowed(request.method, request.url.path.replace("/api/v2/goview", "")):
    return None
  token = extract_token(request)
  if not token:
    raise HTTPException(status_code=401, detail="token overdue")
  payload = decode_access_token(token)
  user = session.get(User, payload.get("sub"))
  if not user:
    raise HTTPException(status_code=401, detail="token overdue")
  return user

def optional_token(request: Request, session = Depends(get_session)):
  token = extract_token(request)
  if not token:
    return None
  payload = decode_access_token(token)
  return session.get(User, payload.get("sub"))

# app 层统一异常处理，将 HTTPException 转为 {code,msg,data}
# @app.exception_handler(HTTPException)
# def http_exc_handler(request, exc):
#     if exc.detail == "token overdue":
#         return JSONResponse(status_code=200, content=error(886, "token overdue"))
#     return JSONResponse(status_code=200, content=error(500, str(exc.detail)))
```

### 11.10 deps.py 中间件与异常处理（完整示例）

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

from tricys_backend.api.v2.goview.responses import error

def register_goview_handlers(app: FastAPI):
  @app.exception_handler(HTTPException)
  async def goview_http_exception_handler(request: Request, exc: HTTPException):
    # 统一成 code/msg/data 格式
    if str(exc.detail) == "token overdue":
      return JSONResponse(status_code=200, content=error(886, "token overdue"))
    return JSONResponse(status_code=200, content=error(500, str(exc.detail)))

  @app.middleware("http")
  async def goview_response_wrapper(request: Request, call_next):
    response = await call_next(request)
    return response
```

### 11.11 responses.py 伪实现（统一响应）

```python
class ResultCode:
  SUCCESS = 200
  TOKEN_OVERDUE = 886
  SERVER_ERROR = 500

def success(data=None, msg="success"):
  return {"code": ResultCode.SUCCESS, "msg": msg, "data": data}

def error(code, msg):
  return {"code": code, "msg": msg, "data": None}
```

### 11.12 file save 伪实现（上传保存）
### 11.13 project.py 分页返回 meta 结构

```python
# 建议统一返回结构：
# {
#   "code": 200,
#   "msg": "success",
#   "data": [ ... ],
#   "meta": {"page": 1, "pageSize": 20, "total": 100}
# }

return {
  "code": 200,
  "msg": "success",
  "data": data,
  "meta": {"page": page, "pageSize": pageSize, "total": total}
}
```

### 11.14 上传文件类型/大小白名单策略

```python
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MAX_SIZE_MB = 10

def validate_upload(file: UploadFile):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="invalid file type")
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large")
```

```python
from pathlib import Path
import shutil
import uuid

ASSETS_DIR = Path("tricys_backend/assets/goview")

def save_to_assets(upload_file: UploadFile) -> str:
  ASSETS_DIR.mkdir(parents=True, exist_ok=True)
  filename = upload_file.filename or "upload.bin"
  safe_name = f"{uuid.uuid4().hex}_{filename}"
  target = ASSETS_DIR / safe_name
  with target.open("wb") as f:
    shutil.copyfileobj(upload_file.file, f)
  return str(target)
```

---

## 12. 错误码、白名单与安全要点

- 白名单：sys/login, sys/getOssInfo, project/getData
- token 失效：code=886
- 其余接口必须带 token header
- 建议 HTTP status 统一 200，错误由 code/msg 表达
- CORS 允许 tricys_visual 与 tricys_goview origin

---

## 13. 实施步骤（最小改动集）

1. 增加 /api/v2/goview 路由模块。
2. 新增 GoviewProject 数据模型与 CRUD 服务。
3. 实现 sys/project 接口与响应封装。
4. 挂载 assets/goview 静态资源。
5. 配置 GoView 前端前缀与环境变量。
6. 采用 iframe 方案 B 并传入 apiBase。

---

## 14. 测试与验证

- 登录 JSON / form。
- CRUD：create -> save -> getData -> publish。
- token 过期返回 code=886。
- 上传文件返回可访问 fileurl。
- iframe 正常加载并完成请求。

---

## 15. 文件改动清单

前端：
- tricys_goview/src/settings/httpSetting.ts
- tricys_goview/.env
- tricys_visual/src/views/GoviewView.vue
- tricys_visual/.env

后端：
- tricys_backend/api/v2/goview/*
- tricys_backend/models/goview_project.py
- tricys_backend/services/goview_project_service.py
- tricys_backend/main.py（静态资源、CORS、路由挂载）

---

## 16. 参考资料

- GoView master-fetch README
- tricys_goview API path files

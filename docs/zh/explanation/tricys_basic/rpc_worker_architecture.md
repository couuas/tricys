## 1. 背景与目标

TRICYS 当前的协同仿真机制已经具备良好的插件边界：阶段一仿真先生成输入 CSV，外部处理器（Handler）再生成输出 CSV 和端口映射，最后由拦截器机制把外部结果重新注入 Modelica 模型。

现有问题不在于 Handler 不可扩展，而在于 Handler 的执行方式仍然默认绑定到 `tricys` 进程本地。对于 `win32com.client`、Aspen COM、部分 COMSOL 接口或其他依赖宿主机专有环境的软件，这种“进程内动态导入”的方式会把运行平台、依赖安装和许可证环境直接耦合到 TRICYS 主执行环境中，难以与 Docker 场景兼容。

因此，RPC Worker 架构的目标不是替代现有协同仿真流程，而是把 Handler 的执行后端从“本地进程内插件”升级为“本地或远程的统一执行运行时”，让第三方接口开发者只实现自己的核心求解逻辑，而无需重复处理服务化集成问题。

## 2. 总体设计原则

该架构遵循以下原则：

- 保留 TRICYS 现有协同仿真的主流程：阶段一仿真、Handler 执行、拦截器集成、阶段二仿真。
- 将第三方工具调用与服务化集成逻辑彻底解耦。
- 统一作业生命周期、资产传输、日志、超时、并发、取消、结果回传等横切能力。
- 让 Aspen、COMSOL 或其他第三方插件都遵循同一套最小扩展协议。
- 保持对现有本地 Handler 的兼容，RPC 只是新增的执行后端，而不是重写配置体系。

## 3. 四层 RPC 架构

推荐将远程 Handler 能力拆分为四层：

```text
┌────────────────────────────────────────────┐
│ 第 1 层：TRICYS Remote Transport           │
│ 在协同仿真流程中发起远程调用并回收结果     │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│ 第 2 层：Worker Runtime                    │
│ 负责任务生命周期、资产、日志、超时、队列   │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│ 第 3 层：Solver Plugin SDK                 │
│ 为 Aspen/COMSOL 等插件提供统一扩展接口     │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│ 第 4 层：Tool Adapter / Manifest           │
│ 声明插件能力、参数、资产、平台与并发约束   │
└────────────────────────────────────────────┘
```

### 3.1. 第 1 层：TRICYS Remote Transport

这一层位于 TRICYS 协同仿真主流程内部，负责将“执行 Handler”这一步从本地 `import + function call` 替换为统一的远程调用。

它的职责包括：

- 读取 `co_simulation.handlers` 中声明的远程执行配置。
- 将阶段一仿真生成的输入 CSV、参数和资产清单打包为远程作业请求。
- 向 RPC Worker 提交任务，并轮询或订阅任务状态。
- 把远端返回的输出 CSV 落地到当前 job workspace。
- 将远端返回的结构化结果转换为 TRICYS 现有的 `output_placeholder` 语义。

这一层不应关心 Aspen COM、COMSOL API、Windows 服务管理等第三方实现细节。它只面向 TRICYS 协同仿真契约。

### 3.2. 第 2 层：Worker Runtime

Worker Runtime 是通用 RPC Worker 的核心，其职责是承接所有与业务插件无关的横切逻辑。

它至少需要统一处理以下能力：

- 作业接收与校验
- 身份认证与来源控制
- 工作目录创建与清理
- 输入文件与资产落地
- 日志采集与流式输出
- 超时控制与取消执行
- 并发限制与排队调度
- 错误标准化与结果打包
- 能力发现与健康检查

运行时不应理解 TRICYS 的拦截器细节，也不应内嵌 Aspen 或 COMSOL 的专有逻辑。它的定位是一个“通用求解器执行运行时”。

### 3.3. 第 3 层：Solver Plugin SDK

插件 SDK 面向第三方工具开发者，其目标是将插件开发约束为“只实现核心逻辑”。

插件作者应当只需要处理：

- 如何读取本地工作目录中的输入文件
- 如何调用第三方软件执行求解
- 如何输出标准结果文件或结构化结果

插件作者不应重复处理：

- HTTP 路由
- 文件上传与下载
- token 认证
- 日志协议
- 超时、重试、取消
- 作业状态机
- TRICYS 的配置细节

一个推荐的插件执行抽象如下：

```python
class ExecutionContext:
    job_id: str
    workspace_dir: str
    params: dict
    inputs: dict
    assets: dict
    output_dir: str
    logger: object


class ExecutionResult:
    status: str
    output_artifacts: dict
    structured_outputs: dict
    metrics: dict
    warnings: list[str]
```

插件只面对 `ExecutionContext` 和 `ExecutionResult` 这类本地语义，而不直接面对网络请求体。

### 3.4. 第 4 层：Tool Adapter / Manifest

每个插件除了核心执行逻辑，还应有一份声明式清单（Manifest），用于描述其静态能力和运行要求。

典型字段包括：

- 插件名称与版本
- 支持的操作（operation）列表
- 参数 schema
- 输入资产 schema
- 输出产物 schema
- 所需平台与依赖软件版本
- 默认超时
- 最大并发数
- 许可证或外部环境要求

Manifest 的意义在于：

- 让 TRICYS 在任务提交前做静态校验
- 让 Worker Runtime 在运行前做预检
- 让前端或配置系统能自动生成参数表单和说明

## 4. 推荐的数据与执行模型

### 4.1. 统一作业模型

建议 Worker 使用统一的“提交任务 - 查询状态 - 获取产物”模型，而不是直接暴露“远程执行某个 Python 函数”。

一个通用作业请求应至少包含：

- `job_id`、`trace_id` 等调试标识
- `plugin_name` 和 `operation_name`
- 结构化 `params`
- 超时、优先级、重试等执行策略
- 输入文件与资产引用
- 输出要求与回传策略

响应建议拆分为异步任务接口：

- `submit_job`
- `get_job_status`
- `get_job_logs`
- `get_job_artifacts`
- `cancel_job`

对 Aspen、COMSOL 这类长时间运行、并发能力有限、可能受许可证约束的工具而言，异步任务模型比同步阻塞接口更稳妥。

### 4.2. 统一资产模型

资产系统应该是 RPC Worker 的一等公民。建议支持三种资产来源：

- `inline`：小文件随请求直接传输，适合输入 CSV、少量 JSON。
- `upload`：先上传文件，再在作业请求中引用 `asset_id`。
- `reference`：只传逻辑引用，由 Worker 在本地解析为真实路径，适合大型模型文件、许可证资源或固定安装目录。

对 Aspen 和 COMSOL 这类依赖本地环境和大文件的插件，`reference` 模式通常应作为主路径，而不是每次从 TRICYS 容器上传完整宿主机资产。

## 5. 与 TRICYS 协同仿真的对接方式

RPC Worker 的引入不应改变 TRICYS 的协同仿真主语义，只替换 Handler 的执行方式。

集成逻辑建议如下：

1. TRICYS 仍然执行阶段一仿真，生成输入 CSV。
2. Remote Transport 将输入 CSV、参数和资产说明提交给 Worker。
3. Worker Runtime 调用目标插件，执行第三方求解器逻辑。
4. Worker 返回输出 CSV 和结构化结果。
5. TRICYS 将输出 CSV 放回本地 job workspace。
6. TRICYS 继续调用现有拦截器机制完成阶段二仿真。

由此可见，RPC Worker 是对“Handler 执行边界”的扩展，而不是对“拦截器机制”或“阶段一/阶段二仿真流程”的替代。

## 6. 为什么这套设计适合 Docker + 宿主机混合部署

该架构最直接的价值，在于允许 TRICYS 主流程继续运行在 Linux Docker 中，同时把平台依赖型插件放在 Windows 宿主机或其他远程节点。

典型部署方式如下：

- `tricys` 与 `tricys-backend` 运行于 Linux 容器。
- Aspen Worker 运行于 Windows 主机，具备本地 COM、Aspen 安装和许可证环境。
- COMSOL Worker 可运行于另一个具备 COMSOL 环境的专用节点。
- TRICYS 通过统一 RPC 协议调用这些节点，而不再直接导入其 Python 依赖。

这样可以把平台差异、许可证环境和第三方软件安装要求收敛到 Worker 节点，而不是扩散到主容器镜像。

## 7. 推荐的最小可用版本

为了控制复杂度，第一阶段建议只落地最小可用版本：

- 一个通用 Worker Runtime
- 一套最小插件 SPI
- 一份插件 Manifest 规范
- 一组基础任务接口：提交、状态、日志、产物、取消
- 一个 Aspen 参考插件
- TRICYS 侧一个 Remote Transport 适配层

这已经足以验证核心目标：新接入一个第三方工具时，开发者只编写插件核心逻辑，而不再重写集成框架。

## 8. 设计结论

TRICYS 的协同仿真现有边界已经足够清晰，真正需要抽象提升的不是仿真流程本身，而是 Handler 的执行后端。

通过引入“四层 RPC 架构”，可以将：

- TRICYS 继续定位为仿真流程编排者
- Worker Runtime 定位为通用远程执行运行时
- Solver Plugin 定位为第三方工具核心逻辑承载体
- Manifest 定位为能力声明与静态契约层

最终实现“核心逻辑与集成逻辑分离”的目标，为 Aspen、COMSOL 以及后续任何第三方接口提供一致的接入路径。
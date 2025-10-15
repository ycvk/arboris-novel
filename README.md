# Arboris |  AI 写作伙伴，点亮你的创作灵感

你是否曾面对空白的文档，灵感枯竭？是否曾被宏大的故事设定、错综复杂的人物关系搞得焦头烂额？

**Arboris** 为每一位小说家而生。它不仅仅是一个写作工具，更是你的专属 AI 创意伙伴，致力于将你从繁琐的构思与整理工作中解放出来，让你专注于创作本身——那个最激动人心的部分。

**在线体验:** [https://arboris.aozhiai.com](https://arboris.aozhiai.com)

**交流群:** 

<img width="306" height="304" alt="屏幕截图 2025-10-12 221806" src="https://github.com/user-attachments/assets/e0315a7b-1138-4af3-9c5b-0e519c1705e5" />

---
<img width="555" height="666" alt="image" src="https://github.com/user-attachments/assets/05974659-3172-4188-95d1-16bdf269d0c6" />
<img width="811" height="515" alt="image" src="https://github.com/user-attachments/assets/aebe5ddb-3efb-4acd-a160-46df2bf928aa" />
<img width="1471" height="880" alt="image" src="https://github.com/user-attachments/assets/a52d0214-bc1b-4792-8a2b-267b09e47379" />
<img width="1375" height="872" alt="image" src="https://github.com/user-attachments/assets/0673faad-43df-4479-83ae-cffa870199a3" />
<img width="1392" height="852" alt="image" src="https://github.com/user-attachments/assets/b7a7af24-1689-4341-aa78-26b0d74bdddd" />
<img width="1240" height="879" alt="image" src="https://github.com/user-attachments/assets/137d44eb-3afa-4a0d-b88f-a62ff3621944" />
<img width="1255" height="882" alt="image" src="https://github.com/user-attachments/assets/c831d746-8c1a-4ce8-aa1c-9b852da15c11" />

---

## ✨ Arboris 能为你做什么？

在这里，你只需提出一个模糊的想法，AI 就能为你……

- **🌱 孕育世界**: 从零开始构建一个全新的世界观，包括独特的派系、关键的地点和丰富的背景设定。
- **🎭 塑造角色**: 创造有血有肉的角色，并用一张清晰的关系网将他们联系起来，让人物关系一目了然。
- **🗺️ 规划蓝图**: 将灵感火花扩展成完整的故事大纲，从开端、发展到高潮，情节脉络清晰可见。
- **✍️ 挥洒文墨**: 在你的指导下，AI 可以撰写完整的章节草稿。它会提供多个版本供你挑选、修改，如同与一位不知疲倦的写手并肩作战。

### 核心亮点

- **交互式写作台**: 一个沉浸式的创作空间，你可以在这里与 AI 对话、下达指令、编辑和优化生成的文本。
- **版本与评估**: AI 生成的每个草稿都会被妥善保存。你可以对比不同版本，标记出满意的部分，教会 AI 更懂你的风格。
- **项目式管理**: 将每部小说作为一个独立项目进行管理，所有设定、大纲、章节都井井有条，告别混乱。
- **高度可定制**: 从驱动 AI 的核心提示词（Prompt）到模型的 API 设置，一切尽在你的掌控之中。你可以通过后台轻松调整，让 Arboris 更符合你的创作习惯。
- **一键部署**: 我们提供完整的 Docker 配置，只需一条命令，即可在你自己的服务器上拥有一个专属的 AI 写作助手。


## 🚀 立即开始

拥有自己的 Arboris 过程非常简单。

### 准备环境
- 复制环境变量模板：`cp .env.example .env`
- 根据部署环境调整 `.env` 内的数据库、SMTP、OpenAI 及开关配置。

### 使用官方镜像
- 已推送镜像：`tichui251/arboris-app:latest`
- 推荐执行 `docker pull tichui251/arboris-app:latest` 获取最新版本。
- 镜像标签已在 `docker-compose.yml` 中配置，如需固定版本可自行修改。

### 使用 Docker Compose 启动
1. 确认 `.env` 与 `docker-compose.yml` 位于同一目录。
2. 默认使用 SQLite（无需数据库服务），直接执行：
   ```bash
   docker compose up -d
   ```
   > 如需将 SQLite 数据库文件映射到宿主机路径，可在 `.env` 中设置 `SQLITE_STORAGE_SOURCE=./storage` 或绝对路径。
3. 若需启用内置 MySQL，请在命令前设置 `DB_PROVIDER=mysql` 并启用 `mysql` profile：
   ```bash
   DB_PROVIDER=mysql docker compose --profile mysql up -d
   ```
4. 若连接外部 MySQL，同样需设置 `DB_PROVIDER=mysql`，但无需开启 profile：
   ```bash
   DB_PROVIDER=mysql docker compose up -d
   ```

### 环境变量摘要
| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `APP_PORT` | 否 | 映射到宿主机的 HTTP 端口，默认 `80`。 |
| `SECRET_KEY` | 是 | JWT 加密密钥，需设置为随机且足够复杂的字符串。 |
| `ENVIRONMENT` | 否 | 运行环境标识，默认 `production`。 |
| `DEBUG` | 否 | 是否启用调试日志，默认 `false`。 |
| `DB_PROVIDER` | 否 | 数据库类型，默认 `sqlite`；切换为 `mysql` 时请配合相关命令。 |
| `SQLITE_STORAGE_SOURCE` | 否 | SQLite 数据存储映射；留空使用命名卷，或设置为宿主机路径/其他卷名。 |
| `MYSQL_HOST` | 是 | 数据库主机地址，使用内置 MySQL 时保持为 `db`。 |
| `MYSQL_PORT` | 否 | 数据库端口，默认 `3306`。 |
| `MYSQL_USER` | 是 | 应用使用的数据库用户名。 |
| `MYSQL_PASSWORD` | 是 | 应用数据库密码。 |
| `MYSQL_DATABASE` | 是 | 应用数据库名称，默认 `arboris`。 |
| `MYSQL_ROOT_PASSWORD` | 使用内置数据库时必填 | 内置 MySQL 的 root 密码，外部数据库部署可忽略。 |
| `ADMIN_DEFAULT_USERNAME` | 否 | 首次启动的管理员用户名，默认 `admin`。 |
| `ADMIN_DEFAULT_PASSWORD` | 否 | 首次启动的管理员密码，部署后请尽快修改。 |
| `ADMIN_DEFAULT_EMAIL` | 否 | 管理员默认邮箱 |
| `OPENAI_API_KEY` | 视业务需求 | LLM 密钥，用于AI生成,必填。 |
| `OPENAI_API_BASE_URL` | 是 | LLM API 地址，默认官方 `https://api.openai.com/v1`。 |
| `OPENAI_MODEL_NAME` | 是 | 调用的模型名称，默认 `gpt-3.5-turbo`。 |
| `WRITER_CHAPTER_VERSION_COUNT` | 否 | 作家模式中保留的章节版本数量，默认 `2`。 |
| `SMTP_SERVER` | 否（开启注册时必填） | SMTP 服务器地址。 |
| `SMTP_PORT` | 否 | SMTP 端口，默认 `465`（SSL）。 |
| `SMTP_USERNAME` | 必填（开启邮件时） | SMTP 登录账号。 |
| `SMTP_PASSWORD` | 必填（开启邮件时） | SMTP 登录密码或授权码。 |
| `EMAIL_FROM` | 否 | 邮件显示的发件人名称，默认 “拯救小说家”。 |
| `ALLOW_USER_REGISTRATION` | 否 | 是否开放用户自助注册，默认 `false`。 |
| `ENABLE_LINUXDO_LOGIN` | 否 | 是否开启 Linux.do OAuth 登录，默认 `false`。 |
| `LINUXDO_CLIENT_ID` | 启用 Linux.do 时必填 | OAuth Client ID。 |
| `LINUXDO_CLIENT_SECRET` | 启用 Linux.do 时必填 | OAuth Client Secret。 |
| `LINUXDO_REDIRECT_URI` | 启用 Linux.do 时必填 | 授权回调地址，应指向 `/api/auth/linuxdo/register`。 |
| `LINUXDO_AUTH_URL` | 否 | 授权地址，默认官方地址。 |
| `LINUXDO_TOKEN_URL` | 否 | 获取 token 的地址，默认官方地址。 |
| `LINUXDO_USER_INFO_URL` | 否 | 用户信息查询地址，默认官方地址。 |

> 其余可选参数与示例说明详见 `.env.example` 注释。


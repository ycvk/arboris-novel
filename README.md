# 部署指南

## 准备环境
- 复制环境变量模板：`cp .env.example .env`
- 根据部署环境调整 `.env` 内的数据库、SMTP、OpenAI 及开关配置。

## 使用官方镜像
- 已推送镜像：`tichui251/arboris-app:latest`
- 推荐执行 `docker pull tichui251/arboris-app:latest` 获取最新版本。
- 镜像标签已在 `docker-compose.yml` 中配置，如需固定版本可自行修改。

## 使用 Docker Compose 启动
1. 确认 `.env` 与 `docker-compose.yml` 位于同一目录。
2. 若需要内置 MySQL，执行（推荐内置）：
   ```bash
   docker compose --profile with-db up -d
   ```
3. 若使用外部数据库，执行：
   ```bash
   docker compose up -d
   ```

## 环境变量摘要
| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `APP_PORT` | 否 | 映射到宿主机的 HTTP 端口，默认 `80`。 |
| `SECRET_KEY` | 是 | JWT 加密密钥，需设置为随机且足够复杂的字符串。 |
| `ENVIRONMENT` | 否 | 运行环境标识，默认 `production`。 |
| `DEBUG` | 否 | 是否启用调试日志，默认 `false`。 |
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

# Agent 约定

## Git 同步

对本仓库（detection）的代码改动完成后，**无需用户再要求**，自动：

1. `git add` 相关文件（勿提交 `.env`、密钥、上传/导出数据）
2. 按仓库风格写 commit message 并 commit
3. `git push origin` 当前分支

仅当用户明确说「不要推送 / 先别提交」时跳过。

## 服务器部署

Ubuntu 服务器统一通过 `ssh opencode-server` 连接。

- 项目目录：`/www/wwwroot/detection`
- 部署方式：Docker Compose，更新流程：
  ```
  ssh opencode-server
  cd /www/wwwroot/detection
  git pull origin main
  docker compose up -d --build
  ```
- 健康检查：`curl http://127.0.0.1:8000/api/health`
- 服务器上还有另一个项目 `fcl-quote-system`（`/www/wwwroot/FCL-Quote/deploy`，Compose 项目名 `fcl-quote-system`）。

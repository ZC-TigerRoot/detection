# Agent 约定

## Git 同步

对本仓库（detection）的代码改动完成后，**无需用户再要求**，自动：

1. `git add` 相关文件（勿提交 `.env`、密钥、上传/导出数据）
2. 按仓库风格写 commit message 并 commit
3. `git push origin` 当前分支

仅当用户明确说「不要推送 / 先别提交」时跳过。

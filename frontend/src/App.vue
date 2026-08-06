<template>
  <el-container class="layout">
    <el-header class="header" height="56px">
      <div class="brand" @click="$router.push('/')">
        <div class="brand-icon">🌿</div>
        <span class="brand-text">环境监测方案管理系统</span>
      </div>
      <div class="header-right">
        <el-button
          link
          @click="$router.push('/settings')"
          style="color: #fff; font-size: 14px"
        >
          ⚙️ 设置
        </el-button>
        <span class="header-desc">智能导入 · 快速校对 · 一键导出</span>
      </div>
    </el-header>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100%;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  color: #fff;
  padding: 0 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: opacity 0.2s;
}
.brand:hover {
  opacity: 0.85;
}
.brand-icon {
  font-size: 24px;
  line-height: 1;
}
.brand-text {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.3px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-desc {
  font-size: 13px;
  opacity: 0.7;
  font-weight: 400;
}
.main {
  padding: 0;
  overflow: auto;
}
</style>

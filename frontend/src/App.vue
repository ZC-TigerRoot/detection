<template>
  <el-container class="layout">
    <el-header class="header" height="56px">
      <div class="brand" @click="$router.push('/')">环境监测方案管理系统</div>
      <div class="header-right">导入 · 校对 · 导出</div>
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
  background: #1f2d3d;
  color: #fff;
  padding: 0 24px;
}
.brand {
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}
.header-right {
  font-size: 13px;
  opacity: 0.75;
}
.main {
  padding: 0;
}
</style>

import { createRouter, createWebHistory } from 'vue-router'
import ProjectList from './views/ProjectList.vue'
import ProjectDetail from './views/ProjectDetail.vue'
import Settings from './views/Settings.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'list', component: ProjectList },
    { path: '/projects/:id', name: 'detail', component: ProjectDetail, props: true },
    { path: '/settings', name: 'settings', component: Settings },
  ],
})

export default router

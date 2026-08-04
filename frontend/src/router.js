import { createRouter, createWebHistory } from 'vue-router'
import ProjectList from './views/ProjectList.vue'
import ProjectDetail from './views/ProjectDetail.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'list', component: ProjectList },
    { path: '/projects/:id', name: 'detail', component: ProjectDetail, props: true },
  ],
})

export default router

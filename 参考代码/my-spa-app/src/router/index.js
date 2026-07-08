import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('../views/AboutView.vue'),
    },
    {
      path: '/articles',
      name: 'articles',
      component: () => import('../views/ArticleList.vue'),
    },
    {
      path: '/articles/:id',
      name: 'article-detail',
      component: () => import('../views/ArticlesDetail.vue'),
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('../views/UserList.vue'),
    },
    {
      path: '/contact',
      name: 'contact',
      component: () => import('../views/ContactView.vue'),
    },
    {
      path: '/user',
      name: 'user',
      component: () => import('../views/UserLayout.vue'),
      meta: { requiresAuth: true, title: '个人中心' },
      children: [
        { path: 'profile', name: 'user-profile', component: () => import('../views/UserProfile.vue') },
        { path: 'settings', name: 'user-settings', component: () => import('../views/UserSettings.vue') },
        { path: 'order', name: 'user-orders', component: () => import('../views/UserOrders.vue') },
        { path: '', redirect: { name: 'user-profile' } }
      ],
    },
    { path: '/home', redirect: '/' },
    { path: '/old-about', redirect: { name: 'about' } },
    {
      path: '/dynamic-redirect',
      redirect: (to) => (to.query.type === 'user' ? '/user/profile' : '/')
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: '登录页面' }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFound.vue'),
      meta: { title: '页面不存在' }
    }
  ],
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth) {
    token ? next() : next({ path: '/login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

router.afterEach((to) => {
  document.title = to.meta.title || '文章管理系统'
})

export default router

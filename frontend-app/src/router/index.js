import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import HomeView from '@/views/HomeView.vue'

// Маршруты экспортируются: тесты создают с ними роутер в памяти.
export const routes = [
  { path: '/', name: 'home', component: HomeView, meta: { requiresAuth: true } },
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
  // Порядок важен: статический /courses/create — раньше динамического /courses/:id.
  // Дополнительно :id ограничен цифрами — «create» не совпадёт с ним в любом порядке.
  {
    path: '/courses/create',
    name: 'course-create',
    component: () => import('@/views/CourseCreateView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/courses/:id(\\d+)',
    name: 'course-detail',
    component: () => import('@/views/CourseDetailView.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/courses/:id(\\d+)/edit',
    name: 'course-edit',
    component: () => import('@/views/CourseEditView.vue'),
    props: true,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Guard выполняется перед каждым переходом. useAuthStore() вызывается ВНУТРИ
// функции: на верхнем уровне модуля Pinia ещё не подключена (app.use(pinia)).
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : undefined }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'home' }
  }
  // Роль нужна, чтобы показать или скрыть кнопки; после перезагрузки её ещё нет.
  if (auth.isAuthenticated && !auth.user) await auth.fetchMe()
  // Страницы создания и редактирования — только для администратора. Это удобство
  // интерфейса: настоящую проверку прав выполняет бэкенд (403).
  if (to.meta.requiresAdmin && auth.user && !auth.isAdmin) {
    return { name: 'home' }
  }
})

export default router

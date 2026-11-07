import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import RootView from '@/views/RootView.vue'

// Маршруты экспортируются: тесты создают с ними роутер в памяти.
//
// meta:
//   requiresAuth      — только для вошедших (иначе /login?redirect=…);
//   requiresModerator — только moderator/admin (UX; настоящая проверка — 403 бэкенда);
//   guestOnly         — вошедшего пользователя отправляем на главную.
export const routes = [
  // Лаб. № 8: «/» публичный — гость видит лендинг, вошедший — список курсов.
  { path: '/', name: 'home', component: RootView },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/check-email',
    name: 'check-email',
    component: () => import('@/views/CheckEmailView.vue'),
  },
  {
    // Без requiresAuth: у пользователя ещё нет сессии, но есть токен из письма.
    path: '/verify-email',
    name: 'verify-email',
    component: () => import('@/views/VerifyEmailView.vue'),
  },
  {
    // Доступен и при регистрации (cookie registration_token), и из настроек.
    path: '/verify-age',
    name: 'verify-age',
    component: () => import('@/views/AgeVerificationView.vue'),
  },
  {
    path: '/account',
    name: 'account',
    component: () => import('@/views/AccountView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/moderation',
    name: 'moderation',
    component: () => import('@/views/ModerationView.vue'),
    meta: { requiresAuth: true, requiresModerator: true },
  },
  // Порядок важен: статический /courses/create — раньше динамического /courses/:id.
  // Дополнительно :id ограничен цифрами — «create» не совпадёт с ним в любом порядке.
  {
    path: '/courses/create',
    name: 'course-create',
    component: () => import('@/views/CourseCreateView.vue'),
    meta: { requiresAuth: true, requiresModerator: true },
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
    meta: { requiresAuth: true, requiresModerator: true },
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
  // Первый переход ждёт GET /auth/me: только так можно узнать, есть ли
  // сессия (cookie httpOnly — из JS её не видно).
  await auth.init()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : undefined }
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: 'home' }
  }
  if (to.meta.requiresModerator && !auth.canManageContent) {
    return { name: 'home' }
  }
})

export default router

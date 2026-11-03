import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { useToast } from '@/composables/useToast'
import ToastContainer from '@/components/ui/ToastContainer.vue'
import ToastNotification from '@/components/ui/ToastNotification.vue'

beforeEach(() => {
  vi.useFakeTimers()
  useToast().clear()
})
afterEach(() => {
  useToast().clear()
  vi.useRealTimers()
})

describe('useToast', () => {
  it('один массив на всё приложение (singleton)', () => {
    useToast().success('A')
    expect(useToast().toasts.value.map((t) => t.message)).toEqual(['A'])
  })

  it('уведомление исчезает само через заданное время', () => {
    const { toasts, success } = useToast()
    success('Сохранено', 1000)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(999)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(toasts.value).toHaveLength(0)
  })

  it('ошибки держатся дольше успешных (6 с против 3,5 с)', () => {
    const { toasts, success, error } = useToast()
    success('ok')
    error('fail')
    vi.advanceTimersByTime(4000)
    expect(toasts.value.map((t) => t.type)).toEqual(['error'])
  })

  it('remove убирает уведомление и его таймер', () => {
    const { toasts, info, remove } = useToast()
    const id = info('x')
    remove(id)
    expect(toasts.value).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('одновременно не больше пяти уведомлений — старые вытесняются', () => {
    const { toasts, info } = useToast()
    for (let i = 1; i <= 7; i++) info(`#${i}`)
    expect(toasts.value.map((t) => t.message)).toEqual(['#3', '#4', '#5', '#6', '#7'])
  })
})

describe('ToastNotification', () => {
  it('тип задаёт класс и роль: ошибка — alert, остальное — status', () => {
    const err = mount(ToastNotification, { props: { type: 'error', message: 'Сбой' } })
    expect(err.classes()).toContain('toast--error')
    expect(err.attributes('role')).toBe('alert')
    const ok = mount(ToastNotification, { props: { type: 'success', message: 'Готово' } })
    expect(ok.attributes('role')).toBe('status')
  })

  it('клик и кнопка × отправляют close', async () => {
    const w = mount(ToastNotification, { props: { message: 'm' } })
    await w.find('.toast__close').trigger('click')
    expect(w.emitted('close')).toHaveLength(1) // stop: клик не всплывает второй раз
    await w.trigger('click')
    expect(w.emitted('close')).toHaveLength(2)
  })
})

describe('ToastContainer', () => {
  it('показывает уведомления в <body> и закрывает по клику', async () => {
    const w = mount(ToastContainer, { attachTo: document.body })
    useToast().success('Курс создан')
    await nextTick()
    const toast = document.body.querySelector('.toast-container .toast--success')
    expect(toast.textContent).toContain('Курс создан')
    toast.click()
    await nextTick()
    expect(useToast().toasts.value).toHaveLength(0)
    w.unmount()
  })
})

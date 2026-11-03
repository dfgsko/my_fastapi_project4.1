import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'

let wrapper
afterEach(() => wrapper?.unmount())

function open(props = {}, slots = {}) {
  wrapper = mount(BaseModal, {
    props: { open: true, title: 'Удалить?', ...props },
    slots: { default: '<p>Текст</p>', ...slots },
    attachTo: document.body,
  })
  return wrapper
}
const dialog = () => document.body.querySelector('[role="dialog"]')

describe('BaseModal', () => {
  it('телепортируется в <body>, а не остаётся внутри родителя', async () => {
    open()
    await nextTick()
    expect(dialog()).not.toBeNull()
    // Окно — не внутри корня приложения (data-v-app), а прямо в <body>.
    expect(dialog().closest('[data-v-app]')).toBeNull()
    expect(document.body.contains(dialog())).toBe(true)
  })

  it('при open=false ничего не рендерит', async () => {
    open({ open: false })
    await nextTick()
    expect(dialog()).toBeNull()
  })

  it('доступность: aria-modal и заголовок связан через aria-labelledby', async () => {
    open()
    await nextTick()
    const d = dialog()
    expect(d.getAttribute('aria-modal')).toBe('true')
    expect(document.getElementById(d.getAttribute('aria-labelledby')).textContent).toBe('Удалить?')
  })

  it('Escape закрывает окно', async () => {
    open()
    await nextTick()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('клик по фону закрывает, клик внутри окна — нет', async () => {
    open()
    await nextTick()
    dialog().click()
    expect(wrapper.emitted('close')).toBeUndefined()
    document.body.querySelector('.modal-backdrop').click()
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('persistent: во время операции не закрывается ни Escape, ни фоном', async () => {
    open({ persistent: true })
    await nextTick()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    document.body.querySelector('.modal-backdrop').click()
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('закрытое окно не реагирует на Escape (слушатель снят)', async () => {
    open()
    await nextTick()
    await wrapper.setProps({ open: false })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('переносит фокус на элемент с data-autofocus', async () => {
    open({}, { actions: '<button data-autofocus class="cancel">Отмена</button>' })
    await nextTick()
    await nextTick()
    expect(document.activeElement.classList.contains('cancel')).toBe(true)
  })
})

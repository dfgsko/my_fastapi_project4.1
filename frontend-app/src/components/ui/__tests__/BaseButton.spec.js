import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseButton from '@/components/ui/BaseButton.vue'

describe('BaseButton', () => {
  it('рендерит slot', () => {
    const w = mount(BaseButton, { slots: { default: 'Click me' } })
    expect(w.text()).toBe('Click me')
  })

  it('не emit клик при disabled', async () => {
    const w = mount(BaseButton, { props: { disabled: true } })
    await w.trigger('click')
    expect(w.emitted('click')).toBeUndefined()
  })

  it('показывает спиннер при loading и блокирует кнопку', () => {
    const w = mount(BaseButton, { props: { loading: true } })
    expect(w.find('.spinner').exists()).toBe(true)
    expect(w.attributes('disabled')).toBeDefined()
    expect(w.attributes('aria-busy')).toBe('true')
  })

  it('применяет variant и size class', () => {
    const w = mount(BaseButton, { props: { variant: 'danger', size: 'lg' } })
    expect(w.classes()).toContain('base-button--danger')
    expect(w.classes()).toContain('base-button--lg')
  })

  it('по умолчанию primary, md и type="button" (не отправляет форму случайно)', () => {
    const w = mount(BaseButton)
    expect(w.classes()).toEqual(expect.arrayContaining(['base-button--primary', 'base-button--md']))
    expect(w.attributes('type')).toBe('button')
  })

  it('обработчик @click вызывается ровно один раз (атрибуты не дублируются)', async () => {
    const onClick = vi.fn()
    const w = mount(BaseButton, { attrs: { onClick } })
    await w.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('пробрасывает нативные атрибуты на <button> (прозрачная обёртка)', () => {
    const w = mount(BaseButton, {
      props: { type: 'submit' },
      attrs: { 'aria-label': 'Сохранить', 'data-test': 'save' },
    })
    expect(w.element.tagName).toBe('BUTTON')
    expect(w.attributes('type')).toBe('submit')
    expect(w.attributes('aria-label')).toBe('Сохранить')
    expect(w.attributes('data-test')).toBe('save')
  })

  it('отклоняет неизвестный variant (валидатор prop)', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mount(BaseButton, { props: { variant: 'rainbow' } })
    expect(warn.mock.calls.flat().join(' ')).toContain('variant')
    warn.mockRestore()
  })
})

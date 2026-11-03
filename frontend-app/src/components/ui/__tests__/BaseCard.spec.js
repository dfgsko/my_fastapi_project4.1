import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseCard from '@/components/ui/BaseCard.vue'

describe('BaseCard', () => {
  it('рендерит содержимое и слоты header/footer', () => {
    const w = mount(BaseCard, {
      slots: { default: 'Тело', header: 'Шапка', footer: 'Подвал' },
    })
    expect(w.find('.base-card__header').text()).toBe('Шапка')
    expect(w.text()).toContain('Тело')
    expect(w.find('.base-card__footer').text()).toBe('Подвал')
  })

  it('as задаёт тег корня (li для списка)', () => {
    expect(mount(BaseCard, { props: { as: 'li' } }).element.tagName).toBe('LI')
  })

  it('interactive добавляет модификатор для hover-эффекта', () => {
    expect(mount(BaseCard, { props: { interactive: true } }).classes()).toContain(
      'base-card--interactive',
    )
  })
})

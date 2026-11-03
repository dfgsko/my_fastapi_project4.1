import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import BaseInput from '@/components/ui/BaseInput.vue'

describe('BaseInput', () => {
  it('связывает label и input через id', () => {
    const w = mount(BaseInput, { props: { id: 'title', label: 'Название' } })
    expect(w.find('label').attributes('for')).toBe('title')
    expect(w.find('input').attributes('id')).toBe('title')
  })

  it('поддерживает v-model (defineModel)', async () => {
    const Parent = defineComponent({
      components: { BaseInput },
      setup: () => ({ value: ref('старое') }),
      template: '<BaseInput id="x" v-model="value" /><span class="out">{{ value }}</span>',
    })
    const w = mount(Parent)
    expect(w.find('input').element.value).toBe('старое')
    await w.find('input').setValue('новое')
    expect(w.find('.out').text()).toBe('новое')
  })

  it('v-model.number приводит ввод к числу', async () => {
    const Parent = defineComponent({
      components: { BaseInput },
      setup: () => ({ value: ref(1) }),
      template: '<BaseInput id="n" v-model.number="value" type="number" />',
    })
    const w = mount(Parent)
    await w.find('input').setValue('42')
    expect(w.vm.value).toBe(42)
    expect(typeof w.vm.value).toBe('number')
  })

  it('показывает ошибку, подсвечивает поле и связывает их для скринридера', () => {
    const w = mount(BaseInput, { props: { id: 'year', error: 'Слишком большое' } })
    expect(w.find('.error-message').text()).toBe('Слишком большое')
    expect(w.classes()).toContain('base-input--error')
    const input = w.find('input')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-describedby')).toBe('year-error')
  })

  it('без ошибки показывает подсказку и aria-invalid=false', () => {
    const w = mount(BaseInput, { props: { id: 'h', hint: 'Целое число' } })
    expect(w.find('.hint').text()).toBe('Целое число')
    expect(w.find('.error-message').exists()).toBe(false)
    expect(w.find('input').attributes('aria-invalid')).toBe('false')
  })

  it('атрибуты (placeholder, min) идут на input, а не на обёртку', () => {
    const w = mount(BaseInput, { props: { id: 'p' }, attrs: { placeholder: 'Введите', min: '1' } })
    expect(w.find('input').attributes('placeholder')).toBe('Введите')
    expect(w.find('input').attributes('min')).toBe('1')
    expect(w.attributes('placeholder')).toBeUndefined()
  })

  it('multiline рендерит textarea', () => {
    const w = mount(BaseInput, { props: { id: 'd', multiline: true, modelValue: 'текст' } })
    expect(w.find('textarea').element.value).toBe('текст')
    expect(w.find('input').exists()).toBe(false)
  })

  it('required добавляет звёздочку и атрибут', () => {
    const w = mount(BaseInput, { props: { id: 'r', label: 'Поле', required: true } })
    expect(w.find('.required').exists()).toBe(true)
    expect(w.find('input').attributes('required')).toBeDefined()
  })
})

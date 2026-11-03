import { describe, it, expect } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import CourseCard from '@/components/CourseCard.vue'

describe('CourseCard', () => {
  it('показывает поля и ссылку на детали', () => {
    const w = mount(CourseCard, {
      props: {
        course: {
          id: 3,
          title: 'Docker',
          description: 'Контейнеры',
          instructor: 'Петров',
          duration_hours: 8,
        },
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.element.tagName).toBe('LI')
    expect(w.text()).toContain('Docker')
    expect(w.text()).toContain('Петров')
    expect(w.text()).toContain('8 ч')
    expect(w.findComponent(RouterLinkStub).props('to')).toEqual({
      name: 'course-detail',
      params: { id: 3 },
    })
  })
})

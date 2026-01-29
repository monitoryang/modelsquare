import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

describe('Basic Tests', () => {
  it('should pass a simple test', () => {
    expect(1 + 1).toBe(2)
  })

  it('should handle string operations', () => {
    const str = 'Model Square'
    expect(str).toContain('Model')
  })
})

describe('Router Tests', () => {
  it('should render MemoryRouter without crashing', () => {
    render(
      <MemoryRouter>
        <div data-testid="test-element">Test Content</div>
      </MemoryRouter>
    )
    expect(screen.getByTestId('test-element')).toBeInTheDocument()
  })
})

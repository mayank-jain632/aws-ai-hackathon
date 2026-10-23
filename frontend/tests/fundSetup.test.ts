import { describe, expect, test } from 'bun:test'
import { defaults, setupMandate } from '../src/funds/types'

describe('fund setup permissions', () => {
  test('new funds select autonomous live Alpaca paper without changing risk limits', () => {
    const fund = setupMandate()
    expect(fund.mode).toBe('paper')
    expect(fund.trading_allowed).toBe(true)
    expect(fund.approval_required).toBe(false)
    expect([fund.capital, fund.risk, fund.min_cash, fund.max_sector, fund.max_position, fund.max_drawdown]).toEqual([100000, 'balanced', 5, 40, 20, 15])
  })
  test('opening saved historical or restricted funds preserves explicit settings', () => {
    const saved = { ...defaults, name: 'Saved mandate', mode: 'historical', cutoff: '2023-12-01', trading_allowed: false, approval_required: true, capital: 95000, min_cash: 15, max_sector: 30 }
    expect(setupMandate(saved)).toEqual(saved)
    const edited = setupMandate(saved)
    edited.universe.push('TEST')
    expect(saved.universe).not.toContain('TEST')
  })
  test('one new form cannot mutate the next form defaults', () => {
    const first = setupMandate()
    first.universe.pop()
    first.trading_allowed = false
    expect(setupMandate().universe).toEqual(defaults.universe)
    expect(setupMandate().trading_allowed).toBe(true)
  })
})

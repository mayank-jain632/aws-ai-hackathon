import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PaperReceipt } from '../src/funds/PaperOrderReceipts'
import { needsBrokerRefresh, orderRows, pendingExplanation, plannedTrades, receiptStatus, type PaperOrder } from '../src/funds/paperOrders'
const queued: PaperOrder = { symbol:'AAPL', side:'buy', notional:1, status:'accepted', broker_id:'actual-broker-id', client_order_id:'actual-client-id', time:'2026-10-23T21:30:00Z', filled_qty:'0', filled_avg_price:null }
describe('actual paper broker receipts', () => {
  test('accepted orders show their real IDs and never masquerade as fills', () => {
    const html = renderToStaticMarkup(<PaperReceipt order={queued}/>)
    expect(html).toContain('actual-broker-id'); expect(html).toContain('actual-client-id')
    expect(html).toContain('accepted'); expect(html).toContain('No fill reported')
    expect(html).not.toContain('Filled quantity'); expect(html).toContain('Accepted by Alpaca')
  })
  test('actual partial fills and broker timestamps remain distinct from full fills', () => {
    const html = renderToStaticMarkup(<PaperReceipt order={{...queued,status:'partially_filled',filled_qty:'0.5',filled_avg_price:'123.45',filled_at:'2026-10-23T21:31:00Z',submitted_at:'2026-10-23T21:30:01Z'}}/>)
    expect(html).toContain('partially_filled'); expect(html).toContain('0.5'); expect(html).toContain('$123.45'); expect(html).toContain('Broker submitted')
  })
  test('missing submission timestamp is not invented from intent time', () => {
    expect(renderToStaticMarkup(<PaperReceipt order={queued}/>)).toContain('Recorded at')
    expect(renderToStaticMarkup(<PaperReceipt order={queued}/>)).not.toContain('Broker submitted')
  })
  test('saved plans remain distinct and disappear only for matching actual receipt IDs', () => {
    const plan = {kind:'order_plan',time:'2026-10-23T21:00:00Z',strategy_id:'saved-strategy',ready:true,blocked:[],orders:[queued]}
    expect(plannedTrades([plan],[])).toHaveLength(1)
    expect(plannedTrades([plan],[queued])).toHaveLength(0)
    expect(plannedTrades([],[])).toEqual([])
    expect(receiptStatus({...queued,broker_id:undefined,status:'unknown'})).toBe('Submission unconfirmed')
  })
  test('closed-market explanation requires actual clock state, never accepted status alone', () => {
    expect(pendingExplanation(queued)).toBe('Awaiting fill · Not filled')
    expect(pendingExplanation({...queued,market_clock:{is_open:false}})).toBe('Waiting for market open · Not filled')
    expect(pendingExplanation({...queued,status:'filled',filled_qty:'1'})).toBe('')
  })
  test('broker status refresh targets only existing unresolved orders', () => {
    expect(needsBrokerRefresh(queued)).toBe(true)
    expect(needsBrokerRefresh({...queued,status:'filled'})).toBe(false)
    expect(needsBrokerRefresh({...queued,client_order_id:undefined})).toBe(false)
  })
  test('desk dictionary keys recover the actual client id without generating IDs', () => {
    expect(orderRows({'saved-id':{...queued,client_order_id:undefined}})[0].client_order_id).toBe('saved-id')
    expect(orderRows({})).toEqual([])
  })
})

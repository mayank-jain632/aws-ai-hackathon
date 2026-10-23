import { expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { HistoricalTradeReceipts, type HistoricalReplay } from '../src/funds/HistoricalTradeReceipts'
const replay: HistoricalReplay = { mode:'historical_simulation',replay_id:'test-fixture',clock:'2024-01-03',end:'2024-02-01',complete:false,account:{cash:900,equity:1000,positions:{AAPL:100},shares:{AAPL:1}},orders:[{id:'fixture-order',symbol:'AAPL',side:'buy',requested_notional:100,status:'simulated_fill',decision_date:'2024-01-02',fill_date:'2024-01-03',fills:[{date:'2024-01-03',ticker:'AAPL',side:'buy',shares:1,price:100}],skipped:[]}],fills:[] }
test('historical ledger displays virtual values and simulated fills without broker claims', () => {
  const html = renderToStaticMarkup(<HistoricalTradeReceipts replay={replay}/>)
  expect(html).toContain('Historical simulation'); expect(html).toContain('Simulated fill'); expect(html).toContain('Virtual cash');expect(html).toContain('$900.00');expect(html).toContain('Virtual equity');expect(html).toContain('$1,000.00');expect(html).toContain('1 AAPL shares');expect(html).not.toContain('Alpaca');expect(html).not.toContain('Broker order')
})
test('unfilled simulation never claims a fill and preserves actual skip reason', () => {
  const html = renderToStaticMarkup(<HistoricalTradeReceipts replay={{...replay,orders:[{...replay.orders[0],status:'unfilled',fills:[],skipped:[{reason:'volume_cap',detail:'No fill at this session'}]}]}}/>)
  expect(html).toContain('Unfilled in simulation');expect(html).toContain('volume_cap');expect(html).not.toContain('Simulated fill')
})

test('partial simulation is labeled partial even when it has actual fills', () => {
  const html = renderToStaticMarkup(<HistoricalTradeReceipts replay={{...replay,orders:[{...replay.orders[0],status:'simulated_partial_fill'}]}}/>)
  expect(html).toContain('Simulated partial fill')
})

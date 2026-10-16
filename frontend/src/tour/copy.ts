// Final copy supplied in docs/reports/night4-protocol.md. No generated wording.
export const TOUR_COPY = {
  takeTour: 'Take the tour',
  skip: 'Skip tour',
  next: 'Next',
  recorded: 'Recorded example',
  welcome: {
    title: 'Plan a week of ice cream',
    body: "It's Monday 27 July at the Tsing Yi cold store: 75 products, {capacity} pallets of space, and hot days ahead.",
    start: 'Start the tour',
    explore: 'Explore on my own',
  },
  steps: {
    1: { screen: 'Report', big: 'Open "How we found it"', small: 'Scoop flagged value strawberry water ices: {effect}% above forecast.' },
    2: { screen: 'Report', big: 'See where the trend lives', small: 'Strawberry alone: +{l1}%. Add value price: +{l2}%. Add water-based: +{l3}%. The rest barely moved.' },
    3: { screen: 'Report', big: 'Ask Scoop about it', small: 'Pick a question.' },
    4: { screen: 'Report', big: 'Tell Scoop what you know', small: 'Your context is added to the evidence and the order is recalculated.' },
    5: { screen: 'Report', big: 'Review the orders', small: "Scoop has drafted this week's orders for all 75 products." },
    6: { screen: 'Orders', big: 'Check the cold store, then approve', small: '{cases} cases this week · peak {peak} of {capacity} pallets.' },
    7: { screen: 'Watch', big: 'Pick one more thing to watch', small: 'The four tiles at the top are always on.', afterBig: 'Start the week' },
    8: { screen: 'Play', big: 'Watch the week happen', small: "Monday. This week's orders go out at 14:00.", heat: '{date}: the heat arrives. Keep an eye on strawberry stock.', arrival: '{time} {date}: {units} strawberry ices arrive.', stockout: '{time} {date}: {product} runs out.', end: '{end_date}. The order has played out.', afterBig: 'See the results' },
    9: { screen: 'Results', big: "Here's how the week went", small: 'Same cold store, same demand: Scoop against a simple 28-day-average rule.' },
  },
  questions: { why: 'Why strawberry, and why now?', heat: 'Could this just be the heat?' },
  contexts: { summer: 'A summer one-off, ending 10 Aug', growing: 'I expect it to keep growing', unchanged: 'Nothing to add' },
  contextResult: 'Strawberry order: {before} → {after} cases.',
  contextUnchanged: 'Strawberry order stays at {before} cases.',
  widgets: { stock: 'Strawberry stock', space: 'Cold-store space', cover: 'Products closest to running out' },
  end: { title: "That's Scoop", body: 'Now try it with your own choices.', explore: 'Explore on my own', replay: 'Replay the tour' },
} as const;

export function fillTourCopy(template:string,values:Record<string,string|number>) {
  return template.replace(/\{(\w+)\}/g,(_,key:string)=>{
    if(!(key in values))throw new Error(`Missing tour copy value: ${key}`);
    return String(values[key]);
  });
}

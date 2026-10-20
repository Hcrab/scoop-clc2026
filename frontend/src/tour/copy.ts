// User-facing copy for the guided tour; docs/tour-copy.md is the reference.
export const TOUR_COPY = {
  takeTour:'Take the tour',skip:'Skip tour',next:'Next',recorded:'Recorded example',addSelected:'Add selected',
  futureNotice:'In this tour, the next two weeks follow the context you chose.',
  welcome:{title:'Monday, 27 July',body:"You plan stock for the **Tsing Yi cold store**: 75 products, **{capacity} pallets** of space, and this week's orders are due by 2 pm. This tour walks you through **one weekly cycle** in Scoop.",start:'Start the tour',explore:'Explore on my own'},
  steps:{
    1:{title:'Read the weekly report',body:"The left side is the **weekly report**. Every Monday, Scoop's AI writes it from recent store orders: **what changed**, and the evidence behind it. You can open any chart or source to check the numbers."},
    2:{title:'Look at the first finding',body:'The first finding: low-price strawberry water ices are selling **{effect}% above forecast**.'},
    3:{title:'See where the trend comes from',body:'This view shows how the trend was found by **combining several separate tags**. **Weather effects are removed before we measure trends**: a **LightGBM demand forecast** accounts for the weather, and **hierarchical Bayesian trend detection** looks at what is left. So this is a **change in taste**, not the heat, and you can see it more clearly than in a spreadsheet.'},
    4:{title:'Check the suggested actions',body:"The right side lists **suggested actions**. Each card shows what to order more or less of, **how many cases**, and the effect on the cold store. The **in-stock target** at the top sets how much safety stock all orders carry; Scoop sets it automatically from margin and storage cost."},
    5:{title:'Ask the assistant (optional)',body:'If something is unclear, you can **ask the assistant**. It answers from the **same data** as the report.'},
    6:{title:'Add what you know',body:'The data may miss things you know, such as a promotion ending or a one-off event. **Add it here** and Scoop **recalculates the order**.'},
    7:{title:'See how the order changes',body:''},
    8:{title:'Review the orders',body:"Click **Review orders** to see this week's full order."},
    9:{title:'Check the order lines',body:"This page lists **every order line** for this week. Open a line to see how its quantity was calculated: the **forecast**, stock **on hand and on the way**, and any **adjustment**. The bar at the top shows the cold store's **projected peak**."},
    10:{title:'Approve the orders',body:'When the order looks right, click **Approve orders**.'},
    11:{title:'Choose what to follow',body:'This page is where you **follow stock after the order is placed**. The tiles at the top track the **overall health** of the warehouse; the cards below follow **specific products**. Choose the cards to add.'},
    12:{title:'Start the next two weeks',body:'Click **Next: Play** to see how the next two weeks unfold.'},
    13:{title:'Follow the two weeks',body:'This view plays the next two weeks **hour by hour**. The cards update as stock **arrives and sells**; the list on the right records **each event**. You can speed it up with **4×** or **8×**.'},
    14:{title:'Compare the results',body:"This page compares your plan with a **common rule**: order the **28-day average plus 25%**. Both use the **same cold store** and the **same store demand**. Each card shows the rule's result, Scoop's result and the difference."},
  },
  questions:{why:'Why strawberry, and why now?',heat:'Could this just be the heat?',skip:'Skip'},
  contexts:{summer:"It's a summer one-off, ending 10 Aug",growing:'I expect it to keep growing',unchanged:'Nothing to add'},
  recalculation:{
    summer:'With the trend ending on **10 Aug**, Scoop only adds stock for the days before it. Expected lift: **{f_before}× → {f_after}×** · Order: **{before} → {after} cases** · Cold-store peak: **{p_before} → {p_after} pallets**',
    growing:'With the trend expected to grow, Scoop raises its estimate. Expected lift: **{f_before}× → {f_after}×** · Order: **{before} → {after} cases** · Cold-store peak: **{p_before} → {p_after} pallets**',
    growingWithCut:'With the trend expected to grow, Scoop raises its estimate. To stay within the cold store, it trims **{n} cases** from lower-value lines. Expected lift: **{f_before}× → {f_after}×** · Order: **{before} → {after} cases** · Cold-store peak: **{p_before} → {p_after} pallets**',
    unchanged:'No context added, so Scoop keeps the estimate based on the data: **{before} cases**.',
  },
  events:{heat:'{date}: heat begins ({temp}°C).',arrival:'{time} {date}: {units} strawberry ices arrive.',stockout:'{time} {date}: {product} runs out.',endBody:'The two weeks are over. Click **See results**.'},
  widgets:{stock:'Low-price strawberry water ices · stock',space:'Cold-store space',cover:'Products closest to running out'},
  end:{title:'End of the tour',body:"That's one weekly cycle: **read the report**, **add what you know**, **approve the orders** and **follow the results**. You can now explore on your own.",explore:'Explore on my own',replay:'Replay the tour'},
} as const;

export function fillTourCopy(template:string,values:Record<string,string|number>){
  return template.replace(/\{(\w+)\}/g,(_,key:string)=>{if(!(key in values))throw new Error(`Missing tour copy value: ${key}`);return String(values[key]);});
}

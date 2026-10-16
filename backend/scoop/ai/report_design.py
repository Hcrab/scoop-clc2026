"""Structural transport for an AI-authored report, without prose policing."""
from copy import deepcopy
from html.parser import HTMLParser
import re

from pydantic import BaseModel, ConfigDict, Field


class Presentation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=240)
    html:str=Field(min_length=1,max_length=65000)
    css:str=Field(default='',max_length=20000)


GUIDANCE='''Write a serious, clear weekly report, not marketing copy or a data dump.
Author presentation.title, presentation.html (a fragment), and presentation.css. You own the
composition; use the following editorial and visual direction as guidance, not a rigid template.

TITLE AND VOICE
Use a specific finding as the title, with a group, direction and useful comparison or implication.
Example style: "One group exceeds forecast while another softens"; use measured values and names.
Avoid slogans such as "A cooler mix. A different buying plan." The host displays your title and
week above the HTML: don't repeat that heading. Sound like a competent analyst advising a colleague.
State supported observations directly. Explain a working interpretation naturally. Mention uncertainty
once where it changes a decision; avoid repetitive disclaimers, qualifications on every sentence,
and phrases such as "not proof", "cannot rule out" or "before any action" as habitual padding.
Do not mechanically remove these phrases either: a material limitation deserves a specific explanation.

READING ORDER
Organize observations by how clearly they depart from expectation. Clear, pronounced anomalies
belong in Main observations; subtle changes, broadly steady patterns and tentative leads belong
in Secondary observations. Interpret the departure in context using the baseline, normal variation,
sample and persistence, rather than a fixed percentage cutoff. A clear anomaly in a subgroup or
tag intersection is a main observation just as a clear category-wide anomaly is. Business impact
helps explain and order these findings; it does not make a pronounced subgroup anomaly secondary.
Choose this grouping afresh from the evidence, even when a saved narrative used a different order.
Let the evidence determine the number and kinds of observations; neither section has quotas.
1. Main observations: clear departures from expectation, illustrated in aligned cards.
   Each card has a plain group name, small scope/date context, one key number and a compact
   chart. When a fitted effect is supplied, make that estimated effect the one prominent
   data-report-key. Show the recent 14-day requested-versus-forecast deviation and observed
   fill rate, where available, as small muted context with one decimal place. A query-only
   observation without a fitted effect uses its own appropriate measured comparison as the key;
   do not invent a fit. A short paragraph explains what the pattern means or the best explanation worth testing.
   Finish the section with one overall conclusion that advances the reasoning rather than repeating
   the numbers. Avoid putting a KPI strip, a full comparison chart and a prose section all about
   the same facts. One observation has one home.
   Give each distinct new observation its own illustrated card or report block, with its own
   heading, comparison and explanation. A tag combination, local pattern or other special finding
   that adds a separate insight deserves that space; don't bury it in another observation's
   description. Related observations can sit together while retaining their separate identity.
2. Secondary observations: less pronounced changes, meaningful stability and tentative leads.
   Include a useful chart and explain their implication or what to watch next.
   Relevant questions about local events can sit here in one concise conversation prompt.
3. Action recommendations: end the report with only a short list of supplied native action rows.
   Each row already shows the computed Increase / Reduce / Hold direction, illustration, group
   and magnitude; it links to the full explanation in the direction sidebar. These rows are
   the complete action summary. Put analysis in the observation sections and leave purchasing
   quantities and all capacity commentary to the sidebar.
Merge or omit material when evidence warrants. Meaningful stable comparisons belong in the story;
do not manufacture a stable category merely because no alarm fired.

DIVISION OF LABOUR
Charts carry quantities; prose explains meaning; conclusions connect findings; actions say what to do.
Subsequent sections may refer to a group without repeating its statistics. Prefer 1-2 informative
sentences per card to a recital of every query output. Technical IDs, internal coefficients,
calibration details and query arithmetic belong behind the query button. Keep the plain-text report
concise for conversation; it isn't a second visible report. Do not show plan-goal or stage badges.
Keep the report economical while giving each distinct relevant observation enough space to be understood.
Treat source claims as evidence to synthesize, not sentences to copy. A card normally needs one
key estimated effect, when supplied, and an actual/expected graphic; omit extra share statistics and contributor lists
unless they change its explanation. One primary query button per card is enough; related sources
remain available in the evidence index. There is no need for alarm dates in each card subtitle.
For example, summarize a broad pattern and explain whether unmet store requests make it a
replenishment priority. The supporting numbers stay in evidence. Use the supplied native rows
for actions; their direction and magnitude come from the ordering algorithm. Avoid a second
buying table, repeated observations, quantities or a warehouse-capacity paragraph here.
An overlapping subgroup already covered by another action need not get a second row.
Describe an exploratory signal in business terms, such as "Check whether the local uplift continues
next week"; do not refer to internal significance gates in the visible narrative.
Use observed replenishment requests, not claimed consumer sales. Name the comparison: deviation
from forecast is different from change since last week. Separate alarm dates from review windows.
The forecast already contains weather. Interpret departures from that expectation using additional
operational evidence or a specific question for the planner, rather than attributing the residual
to temperature again. An estimated service benefit is a projection, not a promise of no shortages.
Keep a group's scope faithful to its definition: examples from a heterogeneous leaf do not make
the entire leaf one product format. Different groups with different effects deserve separate
illustrated observations, even when they are small. Label a positive buying change as an increase.
Use a consistent, familiar price basis in the report. Prefer the catalog's per-item price tier
when describing purchasing groups; introduce price per volume only when that distinction explains
something useful. Overlapping price definitions should not give the same products confusing labels.
When a broader card's explanation reveals a pronounced local or intersecting subgroup anomaly,
give that finding its own card and comparison rather than leaving its discovery in the paragraph.

VISUAL DIRECTION
Warm off-white background, white cards, dark green text, muted green / coral / violet accents.
Use sentence case and the normal dark-green heading colour for section headings, including
merchandising and planning checks. Reserve accent colours for data and graphics.
When you raise useful human checks, include them briefly in the report before the final actions.
Use restrained typography, generous but purposeful spacing, equal-width cards and aligned metrics.
Let card widths and column counts follow the content and available space, stacking on a narrow screen.
Arrange native action rows in a compact list that can wrap within the available width.
Place each supplied purchasing adjustment with <figure data-card="cohort" data-id="leaf-0"></figure>,
using the actual id of a supplied cohort card. The host renders a compact clickable row from
the algorithm's direction and magnitude, with the illustration and group name. The click focuses
the corresponding right-hand detail card. Do not author labels or magnitudes around these figures;
do not repeat the rows in a table or prose. Use Q-cohort-<id> as the associated evidence source.
You may still use tables for other analytical data.
Use a host-rendered line chart figure for quantities. The host labels values and units.
Don't decorate all text
with dotted underlines. Query IDs should not be displayed as prominent badges.

CARD INTERACTION CONTRACT (host supplies the JavaScript)
Wrap each observation in an element with data-report-card. Mark its single key metric with
data-report-key and its compact metric/chart block with data-report-summary. Put a small accessible
expand icon button at the top right, data-trend-id="Q2",
using relevant Q evidence. The host expands that same card into a daily actual vs
expected line chart and available time ranges. It only draws prior-year data when supplied. Never
invent dates, time-series points or a last-year curve. Specify a chart as
<figure data-chart="line" data-evidence-id="Q2" data-series="actual,expected"><figcaption>Optional caption</figcaption></figure>.
Only actual, expected and prior series are supported. The host renders the chart from saved
result.daily requested_units/expected_units/prior_year_units, or finding actual_share/expected_share.
Never draw SVG or simulate chart values with inline CSS.
Choose a source whose product intersection, district and measurement match the card. A broader
parent query must not stand in for a subgroup's curve when that subgroup has its own Q source.
At the bottom right, use a small magnifier button data-evidence-id="Q2" with aria-label="View query".
The host opens the query inline. Apply evidence hooks to these dedicated buttons, not the whole card,
paragraph or summary. For native extra explanations you may also use details/summary.
Use only evidence IDs returned by tools. No scripts, event handlers, forms, external resources or
network requests in the generated HTML/CSS.

SKELETON EXAMPLE (layout reference only; substitute real evidence and write your own report):
<section><h2>Main observations</h2><div class="observations">
 <article data-report-card class="observation">
  <header class="card-top"><div><small>All districts</small><h3>Group name</h3></div>
   <button data-trend-id="Q2" aria-label="Expand trend">↗</button></header>
  <div data-report-summary><strong data-report-key><!-- supported estimated effect or query measure --></strong><figure data-chart="line" data-evidence-id="Q2" data-series="actual,expected"></figure></div>
  <p><!-- Meaning or explanation, not the same numbers again --></p>
  <footer><button data-evidence-id="Q2" aria-label="View query">⌕</button></footer>
 </article></div><p class="conclusion"><!-- Integrated conclusion --></p></section>
Suggested CSS: .observations{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:20px}
.observation{background:white;border:1px solid #e0e5dc;border-radius:14px;padding:24px}
.card-top{display:flex;justify-content:space-between;align-items:start;gap:16px}
.observation footer{display:flex;justify-content:flex-end}
@media(max-width:720px){.observations{grid-template-columns:1fr}}
Keep the HTML/CSS economical. This is an example, not mandatory wording or CSS.
'''


def _css(css):
    source=re.sub(r'/\*.*?\*/','',css,flags=re.S)
    # CSS escaping can hide resource functions or imports. It is unnecessary for
    # this bounded report format; native selectors and literal text are supported.
    if '\\' in source or re.search(r'@import\b|(?:expression|(?:-webkit-)?image-set)\s*\(|-moz-binding\s*:|behavior\s*:',source,re.I):
        raise ValueError('Report CSS must not import resources or execute code.')
    for match in re.finditer(r'url\s*\((.*?)\)',source,flags=re.I|re.S):
        target=match.group(1).strip().strip('"\'')
        raise ValueError('Report CSS must not reference resources.')


class _Fragment(HTMLParser):
    allowed=set(('article aside section div span p h1 h2 h3 h4 h5 h6 header footer main nav '
                 'strong em b i u s small mark abbr time br hr ul ol li dl dt dd sup sub '
                 'figure figcaption blockquote pre code details summary table caption thead tbody tfoot tr th td a button').split())

    def __init__(self,ids,evidence=None):
        super().__init__(convert_charrefs=True)
        self.ids=ids
        self.evidence=evidence or {}
        self.tables=[]
        self.table=None
        self.cell=None

    def handle_starttag(self,tag,attrs):
        if tag not in self.allowed:raise ValueError('Unsupported report HTML element: '+tag)
        attributes=dict(attrs)
        if len(attributes)!=len(attrs):raise ValueError('Duplicate report HTML attributes are unsupported.')
        if tag=='table':
            self.table={'caption':'','rows':[]}
            self.tables.append(self.table)
        elif tag=='tr' and self.table is not None:
            self.table['rows'].append([])
        elif tag in {'th','td'} and self.table is not None and self.table['rows']:
            self.cell={'kind':tag,'text':''}
            self.table['rows'][-1].append(self.cell)
        if tag!='figure' and any(key in attributes for key in ('data-chart','data-series')):
            raise ValueError('Chart specifications belong on figure elements.')
        if tag!='figure' and any(key in attributes for key in ('data-card','data-id')):
            raise ValueError('Native card specifications belong on figure elements.')
        if tag=='figure' and ('data-card' in attributes or 'data-id' in attributes):
            if set(attributes) & {'data-chart','data-series','data-evidence-id'}:
                raise ValueError('A figure cannot mix a chart and a native card.')
            card_id=attributes.get('data-id')
            if attributes.get('data-card')!='cohort' or not card_id or any(key not in {'data-card','data-id','class'} for key in attributes):
                raise ValueError('Malformed native cohort card figure.')
            evidence_id='Q-cohort-'+card_id
            source=self.evidence.get(evidence_id,{})
            excluded=source.get('in_card') is False or ('tag_path' in source and not any(step.get('included') for step in source['tag_path']))
            if evidence_id not in self.ids or source.get('id')!=card_id or excluded:
                raise ValueError('Native cohort card must cite a supplied card.')
        if tag=='figure' and 'data-chart' in attributes:
            if attributes.get('data-chart')!='line':raise ValueError('Only line chart figures are supported.')
            source=attributes.get('data-evidence-id')
            if source not in self.ids:raise ValueError('Chart must cite returned evidence.')
            series=attributes.get('data-series','').split(',')
            if not series or any(item not in {'actual','expected','prior'} for item in series) or len(set(series))!=len(series):
                raise ValueError('Unsupported chart series.')
            if self.evidence:
                result=self.evidence.get(source,{})
                daily=result.get('daily',[])
                keys={'actual':('requested_units',),'expected':('expected_units',),'prior':('prior_year_units','prior_year_requested_units')}
                available=set()
                if daily:available={item for item,fields in keys.items() if any(any(key in row for key in fields) for row in daily)}
                elif 'actual_share' in result and 'expected_share' in result:available={'actual','expected'}
                if not set(series)<=available:raise ValueError('Chart series are absent from cited evidence.')
        elif tag=='figure' and any(key in attributes for key in ('data-series','data-evidence-id')):
            raise ValueError('Chart figures require data-chart="line".')
        for key,value in attrs:
            value=value or ''
            if key.startswith('on') or key in {'srcdoc','srcset','action','formaction'}:
                raise ValueError('Report HTML must not execute code or request external resources.')
            if key in {'href','src','xlink:href','poster','background'} and value and not value.startswith('#'):
                raise ValueError('Report resources must be inline; use evidence hooks for sources.')
            if key=='style':_css(value)
            if key in {'filter','mask','clip-path','fill','stroke','marker','marker-start','marker-mid','marker-end','cursor'}:_css(value)
            if key in {'data-evidence-id','data-trend-id'} and value not in self.ids:
                raise ValueError('Use only returned evidence IDs in the presentation.')

    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)

    def handle_data(self,data):
        if self.cell is not None:self.cell['text']+=data
        elif self.table is not None:self.table['caption']+=data

    def handle_endtag(self,tag):
        if tag in {'td','th'}:self.cell=None
        elif tag=='table':self.table=None

    def check_adjustment_tables(self):
        cards=[value for key,value in self.evidence.items() if key.startswith('Q-cohort-') and isinstance(value,dict) and 'id' in value]
        for table in self.tables:
            rows=table['rows']
            headings=next(([cell['text'] for cell in row] for row in rows if any(cell['kind']=='th' for cell in row)),
                          [cell['text'] for cell in rows[0]] if rows else [])
            columns=[i for i,heading in enumerate(headings) if re.search(r'\b(cases?|pallets?)\b',heading,re.I)]
            context=' '.join(headings)+' '+table['caption']
            adjustment=bool(re.search(r'\b(change|adjust(?:ment)?|increase|reduce|decrease|add|remove|buy|purchase|order|proposed)\b',context,re.I))
            for row in rows:
                if any(cell['kind']=='th' for cell in row):continue
                values=[cell['text'] for cell in row]
                for card in cards:
                    matched=set()
                    for i in columns:
                        if i>=len(values):continue
                        heading=headings[i].lower()
                        target=card.get('pallet_change') if 'pallet' in heading else card.get('case_change')
                        if target is None:continue
                        tokens=re.findall(r'(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.])',values[i].replace('−','-'))
                        if any(abs(float(token.replace(',',''))-float(target))<=
                               .5*10**(-len(token.partition('.')[2]))+1e-9 for token in tokens):
                            matched.add('pallet' if 'pallet' in heading else 'case')
                    row_names=' '.join(values).casefold()
                    for token,unit in re.findall(r'(?<![\w.])([-+−]?\d[\d,]*(?:\.\d+)?)\s*(cases?|pallets?)\b',row_names):
                        target=card.get('pallet_change') if unit.startswith('pallet') else card.get('case_change')
                        token=token.replace('−','-')
                        if target is not None and abs(float(token.replace(',',''))-float(target))<=.5*10**(-len(token.partition('.')[2]))+1e-9:
                            matched.add('pallet' if unit.startswith('pallet') else 'case')
                    named=bool(card.get('name') and card['name'].casefold() in row_names)
                    instruction=bool(re.search(r'\b(increase|reduce|decrease|add|remove|trim|buy|purchase|order)\b',row_names))
                    if matched and (adjustment or instruction or len(matched)==2 or named):
                        raise ValueError('Adjustment quantities belong in native cohort cards, not an AI table.')

    def handle_decl(self,decl):raise ValueError('Supply an HTML fragment, not a document declaration.')

    def unknown_decl(self,data):raise ValueError('Unsupported report HTML declaration.')


def validate(value,ids,evidence=None):
    presentation=Presentation.model_validate(value)
    _css(presentation.css)
    parser=_Fragment(set(ids),evidence);parser.feed(presentation.html);parser.close()
    parser.check_adjustment_tables()
    return presentation.model_dump()


def compact_result(result):
    """Model-context copy; the saved trace retains every original row and name."""
    result=deepcopy(result)
    for group in result.get('groups',[]):
        if 'skus' in group:group.pop('members',None)
    cusum=result.get('cusum')
    if isinstance(cusum,dict) and ('daily' in result or 'checks' in cusum):cusum.pop('series',None)
    # The host renders drilldown curves from the full saved card. The analyst
    # needs path effects and sibling comparisons, not repeated copies of every
    # parent/sibling daily series in every function-calling round.
    drilldown=result.get('drilldown')
    if isinstance(drilldown,dict):
        root=drilldown.get('root',{})
        root.pop('daily',None)
        for step in drilldown.get('steps',[]):
            step.pop('daily',None)
            step.pop('rest_daily',None)
    return result

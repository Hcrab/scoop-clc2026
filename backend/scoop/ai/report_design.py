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
   Each card has a plain group name, small scope/date context, one main comparison and a compact
   chart. A short paragraph explains what the pattern means or the best explanation worth testing.
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
3. Action recommendations: a clean aligned list of Increase / Reduce / Hold with the actual group
   names and a brief rationale or next action. If groups overlap, identify which products the action
   targets rather than giving contradictory instructions. Put a material capacity constraint here
   once, alongside what to do about it. Recommendations are clear proposals, not approved purchases.
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
headline deviation and an actual/expected graphic; omit extra share statistics and contributor lists
unless they change its explanation. One primary query button per card is enough; related sources
remain available in the evidence index. There is no need for alarm dates in each card subtitle.
For example, summarize a broad pattern and explain whether unmet store requests make it a
replenishment priority. The supporting numbers stay in evidence. For an action row, describe
the measured adjustment to the forecast and the products it affects, rather than a buying-factor
coefficient, forecast arithmetic, SKU codes or a promised fill rate. Clarify overlapping groups.
Action rows should add the proposed response, not replay the observations. Capacity needs one useful
comparison and an operational response, not a recap of every baseline, preview and allocation number.
Describe an exploratory signal in business terms, such as "Check whether the local uplift continues
next week"; do not refer to internal significance gates in the visible narrative.
Use observed replenishment requests, not claimed consumer sales. Name the comparison: deviation
from forecast is different from change since last week. Separate alarm dates from review windows.
Use a consistent, familiar price basis in the report. Prefer the catalog's per-item price tier
when describing purchasing groups; introduce price per volume only when that distinction explains
something useful. Overlapping price definitions should not give the same products confusing labels.
When a broader card's explanation reveals a pronounced local or intersecting subgroup anomaly,
give that finding its own card and comparison rather than leaving its discovery in the paragraph.

VISUAL DIRECTION
Warm off-white background, white cards, dark green text, muted green / coral / violet accents.
Use restrained typography, generous but purposeful spacing, equal-width cards and aligned metrics.
Let card widths and column counts follow the content and available space, stacking on a narrow screen.
Use a real grid/table for action rows, never variable-width text columns that drift out of alignment.
Use a host-rendered line chart figure for quantities. The host labels values and units.
Don't decorate all text
with dotted underlines. Query IDs should not be displayed as prominent badges.

CARD INTERACTION CONTRACT (host supplies the JavaScript)
Wrap each observation in an element with data-report-card. Mark its compact metric/chart block with
data-report-summary. Put a small accessible expand icon button at the top right, data-trend-id="Q2",
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
  <div data-report-summary><figure data-chart="line" data-evidence-id="Q2" data-series="actual,expected"></figure></div>
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

    def handle_starttag(self,tag,attrs):
        if tag not in self.allowed:raise ValueError('Unsupported report HTML element: '+tag)
        attributes=dict(attrs)
        if tag!='figure' and any(key in attributes for key in ('data-chart','data-series')):
            raise ValueError('Chart specifications belong on figure elements.')
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
                keys={'actual':'requested_units','expected':'expected_units','prior':'prior_year_units'}
                available=set()
                if daily:available={item for item,key in keys.items() if any(key in row for row in daily)}
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
            if key=='style':raise ValueError('Inline CSS is unsupported in report HTML.')
            if key in {'filter','mask','clip-path','fill','stroke','marker','marker-start','marker-mid','marker-end','cursor'}:_css(value)
            if key in {'data-evidence-id','data-trend-id'} and value not in self.ids:
                raise ValueError('Use only returned evidence IDs in the presentation.')

    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)

    def handle_decl(self,decl):raise ValueError('Supply an HTML fragment, not a document declaration.')

    def unknown_decl(self,data):raise ValueError('Unsupported report HTML declaration.')


def validate(value,ids,evidence=None):
    presentation=Presentation.model_validate(value)
    _css(presentation.css)
    parser=_Fragment(set(ids),evidence);parser.feed(presentation.html);parser.close()
    return presentation.model_dump()


def compact_result(result):
    """Model-context copy; the saved trace retains every original row and name."""
    result=deepcopy(result)
    for group in result.get('groups',[]):
        if 'skus' in group:group.pop('members',None)
    cusum=result.get('cusum')
    if isinstance(cusum,dict) and ('daily' in result or 'checks' in cusum):cusum.pop('series',None)
    return result

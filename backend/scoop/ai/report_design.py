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
Example style: "Water-based requests exceed forecast by 28%; chocolate-coated orders soften".
Avoid slogans such as "A cooler mix. A different buying plan." The host displays your title and
week above the HTML: don't repeat that heading. Sound like a competent analyst advising a colleague.
State supported observations directly. Explain a working interpretation naturally. Mention uncertainty
once where it changes a decision; avoid repetitive disclaimers, qualifications on every sentence,
and phrases such as "not proof", "cannot rule out" or "before any action" as habitual padding.
Do not mechanically remove these phrases either: a material limitation deserves a specific explanation.

READING ORDER
1. Main observations: usually two or three meaningful changes, illustrated in aligned cards.
   Each card has a plain group name, small scope/date context, one main comparison and a compact
   chart. A short paragraph explains what the pattern means or the best explanation worth testing.
   Finish the section with one overall conclusion that advances the reasoning rather than repeating
   the numbers. Avoid putting a KPI strip, a full comparison chart and a prose section all about
   the same facts. One observation has one home.
2. Secondary observations: small evidence-led cards explaining why a smaller signal merits attention
   or no immediate adjustment. Include a useful chart and the specific thing to watch next.
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
Aim for an economical report, roughly 350-500 visible words when this amount of evidence warrants it.
Treat source claims as evidence to synthesize, not sentences to copy. A card normally needs one
headline deviation and an actual/expected graphic; omit extra share statistics and contributor lists
unless they change its explanation. One primary query button per card is enough; related sources
remain available in the evidence index. There is no need for alarm dates in each card subtitle.
For example, instead of "all 20 stores...84.7% vs 84.3%...5,152 unfilled...92.3% fill", write
"The increase spans districts and flavours. The stable format mix suggests the shift extends across
the category, while unmet store requests make it a replenishment priority." The numbers stay in evidence.
For an action row, prefer "Plan for water-based demand 15% above forecast; prioritize items with unmet
requests" over a buying-factor coefficient, forecast arithmetic, SKU codes and a promised fill rate.
For an overlapping category, say "Hold non-coated dairy items" rather than listing every SKU.
Action rows should add the proposed response, not replay the observations. Capacity needs one useful
comparison and an operational response, not a recap of every baseline, preview and allocation number.
Describe an exploratory signal in business terms, such as "Check whether the local uplift continues
next week"; do not refer to internal significance gates in the visible narrative.
Use observed replenishment requests, not claimed consumer sales. Name the comparison: deviation
from forecast is different from change since last week. Separate alarm dates from review windows.

VISUAL DIRECTION
Warm off-white background, white cards, dark green text, muted green / coral / violet accents.
Use restrained typography, generous but purposeful spacing, equal-width cards and aligned metrics.
CSS grid is useful: two columns for main findings, three for secondary, stacking on a narrow screen.
Use a real grid/table for action rows, never variable-width text columns that drift out of alignment.
Compact horizontal actual/expected bars or small lines are sufficient; label their values and units.
When bars invite comparison, share a scale or make independent scales clear. Don't decorate all text
with dotted underlines. Query IDs should not be displayed as prominent badges.

CARD INTERACTION CONTRACT (host supplies the JavaScript)
Wrap each observation in an element with data-report-card. Mark its compact metric/chart block with
data-report-summary. Put a small accessible expand icon button at the top right, data-trend-id="Q2",
using the relevant query_group evidence ID. The host expands that same card into a daily actual vs
expected line chart and available time ranges. It only draws prior-year data when supplied. Never
invent dates, time-series points or a last-year curve. The AI can freely design the compact chart.
At the bottom right, use a small magnifier button data-evidence-id="Q2" with aria-label="View query".
The host opens the query inline. Apply evidence hooks to these dedicated buttons, not the whole card,
paragraph, SVG or summary. For native extra explanations you may also use details/summary.
Use only evidence IDs returned by tools. No scripts, event handlers, forms, external resources or
network requests in the generated HTML/CSS; inline SVG and responsive CSS are supported.

SKELETON EXAMPLE (layout reference only; substitute real evidence and write your own report):
<section><h2>Main observations</h2><div class="observations">
 <article data-report-card class="observation">
  <header class="card-top"><div><small>All districts</small><h3>Group name</h3></div>
   <button data-trend-id="Q2" aria-label="Expand trend">↗</button></header>
  <div data-report-summary><!-- One metric and compact labelled chart from Q2 --></div>
  <p><!-- Meaning or explanation, not the same numbers again --></p>
  <footer><button data-evidence-id="Q2" aria-label="View query">⌕</button></footer>
 </article></div><p class="conclusion"><!-- Integrated conclusion --></p></section>
Suggested CSS: .observations{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.observation{background:white;border:1px solid #e0e5dc;border-radius:14px;padding:24px}
.card-top{display:flex;justify-content:space-between;align-items:start;gap:16px}
.observation footer{display:flex;justify-content:flex-end}
@media(max-width:720px){.observations{grid-template-columns:1fr}}
Keep the HTML/CSS economical. The application implements the interactive charts; don't spend output
space manually drawing large historical SVG series. This is an example, not mandatory wording or CSS.
'''


def _css(css):
    source=re.sub(r'/\*.*?\*/','',css,flags=re.S)
    # CSS escaping can hide resource functions or imports. It is unnecessary for
    # this bounded report format; native selectors and literal text are supported.
    if '\\' in source or re.search(r'@import\b|(?:expression|(?:-webkit-)?image-set)\s*\(|-moz-binding\s*:|behavior\s*:',source,re.I):
        raise ValueError('Report CSS must not import resources or execute code.')
    for match in re.finditer(r'url\s*\((.*?)\)',source,flags=re.I|re.S):
        target=match.group(1).strip().strip('"\'')
        if not target.startswith('#'):raise ValueError('Report CSS may reference only inline SVG fragments.')


class _Fragment(HTMLParser):
    allowed=set(('article aside section div span p h1 h2 h3 h4 h5 h6 header footer main nav '
                 'strong em b i u s small mark abbr time br hr ul ol li dl dt dd sup sub '
                 'figure figcaption blockquote pre code details summary table caption thead tbody tfoot tr th td a button '
                 'svg g rect circle ellipse line polyline polygon path text tspan '
                 'defs marker clippath mask pattern lineargradient radialgradient stop '
                 'symbol use title desc').split())

    def __init__(self,ids):
        super().__init__(convert_charrefs=True)
        self.ids=ids

    def handle_starttag(self,tag,attrs):
        if tag not in self.allowed:raise ValueError('Unsupported report HTML element: '+tag)
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

    def handle_decl(self,decl):raise ValueError('Supply an HTML fragment, not a document declaration.')

    def unknown_decl(self,data):raise ValueError('Unsupported report HTML declaration.')


def validate(value,ids):
    presentation=Presentation.model_validate(value)
    _css(presentation.css)
    parser=_Fragment(set(ids));parser.feed(presentation.html);parser.close()
    return presentation.model_dump()


def compact_result(result):
    """Model-context copy; the saved trace retains every original row and name."""
    result=deepcopy(result)
    for group in result.get('groups',[]):
        if 'skus' in group:group.pop('members',None)
    cusum=result.get('cusum')
    if isinstance(cusum,dict) and ('daily' in result or 'checks' in cusum):cusum.pop('series',None)
    return result

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


GUIDANCE='''Author presentation.title as a clear, prominent business headline and presentation.html
as a responsive HTML fragment, with presentation.css for its design. You control the layout;
use the evidence to choose what merits prominence. A warm white background, green, muted
violet and restrained coral can guide the theme lightly. Favor readable type, whitespace,
clear chart labels and layouts that work on narrow screens. Useful ingredients may include
meaningful increases/decreases and evidenced stability, an overall interpretation, human
considerations, lower-priority leads and provisional actions; they are suggestions, not a
mandatory sequence or checklist. Avoid repeating mechanical findings in separate boilerplate.
Use compact charts and expandable evidence where they help. Inline SVG, native details/summary
and CSS hover/focus can make evidence interactive without JavaScript. Include baseline,
time window and district context where needed. An element with data-evidence-id="Q2" (or a
finding ID) lets the host open the corresponding source evidence. Use only available evidence
IDs. The host supplies the outer app and business controls; your report does not apply actions.
Do not display the internal plan goal (such as Margin) or stage as report badges. Keep internal
group codes and buying factors in source evidence; explain their business meaning in the report.
Distinguish deviation from forecast from change over time, and detection dates from window lengths.
Do not include script, event handlers, forms, external resources, network links, imported CSS
or arbitrary JavaScript. No alarm is not evidence of stability: query a comparison before
describing a category as stable. Keep the plain-text report useful and concise for conversation
and legacy readers; the visual presentation can carry richer evidence and context. Let natural
language follow the evidence without forcing specific punctuation, first words or section counts.
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
            if key=='data-evidence-id' and value not in self.ids:
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

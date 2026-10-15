"""Check quantitative claims against the evidence they cite, without judging prose."""
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re


NUMBER = re.compile(r'(?<![\w])(?P<sign>[+\-−])?(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?P<percent>\s*%)?(?![\w])')
DATE = re.compile(r'\b\d{4}-\d{1,2}-\d{1,2}\b')
NATURAL_DATE = re.compile(r'\b(\d{1,2})(?:\s*[–—-]\s*(\d{1,2}))?\s+(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May\w*|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)(?:\s+(20\d\d))?\b', re.I)
MONTHS = {name:i+1 for i,name in enumerate(('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'))}

ID = re.compile(r'\b(?:Q(?:-cohort)?-[\w-]+|Q\d+|T\d+|[A-Za-z][A-Za-z0-9_-]*\d+[A-Za-z0-9_-]*)\b')
UNIT_BASIS = re.compile(r'(?:/|\bper)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ml|kg|g|l)\b',re.I)


def visible_report_claims(report, evidence_ids):
    """Cover displayed copy too; CSS sizing and HTML attributes are not claims."""
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts=[]
        def handle_data(self, data):
            self.parts.append(data)
    parser=Text()
    parser.feed(report.presentation.html)
    return [{'text':text,'evidence_ids':evidence_ids} for text in
            (report.report, report.presentation.title, ' '.join(parser.parts))]


def _numbers(text):
    text = DATE.sub(' ', text)
    text = NATURAL_DATE.sub(' ', text)
    text = ID.sub(' ', text)
    for match in NUMBER.finditer(text):
        try:
            value = Decimal((match.group('sign') or '').replace('−', '-') + match.group('number').replace(',', ''))
        except InvalidOperation:
            continue
        yield value, bool(match.group('percent')), len(match.group('number').partition('.')[2]), match.group().strip()


def _evidence_values(value, *, key=''):
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key in {'id', 'sku', 'group_ids', 'skus', 'tag_path', 'name', 'explanation'}:
                continue
            yield from _evidence_values(child, key=child_key)
    elif isinstance(value, list):
        for child in value:
            yield from _evidence_values(child, key=key)
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return
        if number.is_finite():
            kind='percent' if key.endswith(('_pct', '_percent', '_percentage')) else 'ratio' if any(word in key for word in ('share','rate','ratio','probability','service_level')) or key in {'p_value','q_value'} else 'number'
            yield number, kind
    elif isinstance(value, str) and key in {'date', 'window_start', 'window_end', 'evidence_through', 'cutoff'}:
        return


def _dates(value):
    if isinstance(value, (str,date)) and DATE.fullmatch(str(value)):
        yield str(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in {'date', 'window_start', 'window_end', 'evidence_through', 'cutoff'} and isinstance(child, (str, date)):
                yield str(child)
            else:
                yield from _dates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _dates(child)


def _labels(value):
    if isinstance(value,dict):
        for key,child in value.items():
            if key=='name' and isinstance(child,str):
                yield child
                yield from child.split(' · ')
            else:
                yield from _labels(child)
    elif isinstance(value,list):
        for child in value:yield from _labels(child)


def mismatches(claims, evidence):
    """Return actionable mismatches, scoped to each claim's cited results only."""
    errors = []
    for index, claim in enumerate(claims):
        ids = claim.evidence_ids if hasattr(claim, 'evidence_ids') else claim['evidence_ids']
        text = claim.text if hasattr(claim, 'text') else claim['text']
        values = [item for evidence_id in ids for item in _evidence_values(evidence.get(evidence_id, {}))]
        dates = {item for evidence_id in ids for item in _dates(evidence.get(evidence_id, {}))}
        # Catalog names such as "Lower price / 100 ml" are labels, not a claim
        # that the group ordered 100 units. Only names actually cited are masked.
        quantitative_text=text
        labels={label for evidence_id in ids for label in _labels(evidence.get(evidence_id,{}))}
        bases={(Decimal(match['value']),match['unit'].lower()) for label in labels for match in UNIT_BASIS.finditer(label)}
        quantitative_text=UNIT_BASIS.sub(lambda match:' ' if (Decimal(match['value']),match['unit'].lower()) in bases else match.group(),quantitative_text)
        for label in sorted(labels,key=len,reverse=True):
            if label:quantitative_text=re.sub(re.escape(label),' ',quantitative_text,flags=re.I)
        for found in DATE.findall(text):
            if found not in dates:
                errors.append({'claim_index': index, 'number': found, 'evidence_ids': ids,
                               'reason': 'Date is absent from cited evidence.'})
        for match in NATURAL_DATE.finditer(text):
            month = MONTHS[match.group(3)[:3].lower()]
            year = match.group(4)
            for day in (match.group(1), match.group(2)):
                if day is None:continue
                suffix=f'-{month:02d}-{int(day):02d}'
                if not any(d.endswith(suffix) and (not year or d.startswith(year+'-')) for d in dates):
                    errors.append({'claim_index':index,'number':match.group(),'evidence_ids':ids,
                                   'reason':'Date is absent from cited evidence.'})
        for number, percent, decimals, token in _numbers(quantitative_text):
            tolerance = Decimal('0.5') * (Decimal(10) ** -decimals)
            unsigned=token[0] not in '+-−'
            comparable=[value*100 if percent and kind=='ratio' else value
                        for value,kind in values if not percent or kind in {'percent','ratio'}]
            # "Fell 14.7%" states the magnitude of an evidenced -14.7% change.
            # An explicit opposite sign still fails. Prose is not rewritten.
            matched=any(abs(number-value)<=tolerance or
                        unsigned and value<0 and abs(number+value)<=tolerance for value in comparable)
            if not matched:
                errors.append({'claim_index': index, 'number': token, 'evidence_ids': ids,
                               'reason': 'No cited evidence value matches within displayed rounding.'})
    return errors

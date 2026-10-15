"""Refresh N3 presentation data and re-author the saved report once with Gemini.

Only names, observation projections and report presentation change. Purchase
quantities, physical inputs, planner context, widgets and the spend ledger remain.
"""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path

from sqlalchemy import select

from scoop.ai import gemini, weekly
from scoop.ai.exploration_tools import _groups
from scoop.ai.usage import summary as usage_summary
from scoop.api.service import clean, row
from scoop.cohort_cards import build_observations, cohort_name
from scoop.db import session_scope
from scoop.models import Plan, PurchaseSuggestion, WatchItem
from scoop.simulation_jobs import order_hash


class Figures(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]

    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag=='figure' and values.get('data-card')=='cohort':
            self.ids.append(values.get('data-id'))


def main():
    before_usage=usage_summary()
    payload_sizes=[]

    def wire(payload):
        payload['systemInstruction']['parts'].append({'text':
            'Layout review: the previous draft duplicated native card adjustments inside an Operational Focus table. '
            'Use a list or grid of native figure placeholders with short rationale beside each; the card already shows the name, cases and pallets. '
            'Avoid a second action table. A positive purchase change belongs under Increase, including any remaining lines; do not call it Hold. '
            'Keep group definitions faithful and describe store requests, not inferred retail stockouts or consumer consumption.'})
        payload_sizes.append(len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()))
        return gemini._wire(payload)

    with session_scope() as session:
        plan=session.get(Plan,'P20260720')
        before_hash=order_hash(session,plan)
        before_orders=clean([row(o) for o in session.scalars(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id==plan.id).order_by(PurchaseSuggestion.sku))])
        before_widgets=clean([row(w) for w in session.scalars(select(WatchItem).where(WatchItem.plan_id==plan.id).order_by(WatchItem.id))])
        groups=_groups(session)
        cards=[]
        for saved in (plan.summary or {}).get('cohort_cards',[]):
            if not any(term['included'] for term in saved['tag_path']):
                continue
            card=deepcopy(saved)
            card['name']=cohort_name(card,groups)
            cards.append(card)
        observations=build_observations(plan.summary.get('cohort_model',{}),cards,groups)
        plan.summary={**plan.summary,'cohort_cards':cards,'cohort_observations':observations}
        existing=deepcopy(weekly.view(plan))
        retained=[]
        visible={card['id'] for card in cards}
        for query in existing.get('queries',[]):
            if query.get('name')!='cohort_card':
                retained.append(query)
            elif query['result']['id'] not in visible:
                result={**query['result'],'name':cohort_name(query['result'],groups),'in_card':False}
                retained.append({**query,'name':'cohort_observation','result':result})
        existing['queries']=retained+weekly.program_evidence(plan)
        plan.summary={**plan.summary,'weekly_review':existing}
        result=weekly.upgrade(session,plan,wire=wire,force=True)
        Path('reports/n3-gemini-report.json').write_text(json.dumps(clean(result),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        assert result.get('presentation_upgrade',{}).get('status')=='complete', result.get('presentation_error')
        figures=Figures();figures.feed(result['presentation']['html'])
        assert figures.ids and set(figures.ids)<={card['id'] for card in cards}, 'Missing or unknown native adjustment card'
        plan.summary={**plan.summary,'weekly_review':result}
        assert order_hash(session,plan)==before_hash
        assert before_orders==clean([row(o) for o in session.scalars(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id==plan.id).order_by(PurchaseSuggestion.sku))])
        assert before_widgets==clean([row(w) for w in session.scalars(select(WatchItem).where(WatchItem.plan_id==plan.id).order_by(WatchItem.id))])
        proof={'plan':plan.id,'model':result['presentation_upgrade']['model'],'title':result['presentation']['title'],
               'native_card_ids':figures.ids,'cards':[{'id':card['id'],'name':card['name']} for card in cards],
               'observations':len(observations),'order_hash':before_hash,'orders_and_widgets_unchanged':True,
               'payload_bytes':payload_sizes,'usage_before':before_usage,'usage_after':usage_summary()}
    Path('reports/n3-presentation-refresh.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()

"""One explicitly reviewed Gemini regeneration of the default demo report.

This is editorial review, recorded as such, not a statistical tuning or autonomous eval.
"""
import json
from pathlib import Path
from sqlalchemy import select

from scoop.db import session_scope
from scoop.models import Plan
from scoop.ai import weekly, gemini
from scoop.discussion import _items, _save

FEEDBACK='''Editorial review of the first draft: the weather-adjusted residual was incorrectly
explained by hot weather, two headline blocks repeated one another, two different cohort scopes
were combined under a dairy-tub label, and +43 cases were called Hold. Re-author the report from
the current evidence. Keep a single host-owned title, one informative comparison per card, and
the exact group definitions. Show each distinct observation separately. Use operational queries
when you need evidence for an explanation; ask about missing context rather than assert it.
Keep the plain-text report concise. These are editorial corrections, not an instruction to find
any particular trend or make the policy outperform the rule.'''


def reviewed_wire(payload):
    payload['systemInstruction']['parts'].append({'text':FEEDBACK})
    return gemini._wire(payload)


def main():
    with session_scope() as session:
        plan=session.get(Plan,'P20260720')
        result=weekly.investigate(session,plan,wire=reviewed_wire)
        result['editorial_review']={'feedback':FEEDBACK,'previous_draft':'reports/p6-gemini-report.json',
                                    'method':'Real Gemini regeneration; no manually edited report text.'}
        Path('reports/p6-gemini-reviewed-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if result['status']!='complete':
            print('Review not published:',result['status'],result.get('error'),flush=True)
            return
        session.refresh(plan,with_for_update=True)
        items=[i for i in _items(session,plan) if not(i.get('review_seed') and i.get('status')=='open' and not i.get('note'))]
        for question in result.get('questions',[]):
            qid=plan.id+'-R'+weekly.sha256(question['text'].encode()).hexdigest()[:16]
            if not any(i['id']==qid for i in items):
                items.append({'id':qid,'title':question['text'],'status':'open','finding_id':question['finding_id'],
                              'note':'','managed':True,'review_seed':True})
        _save(plan,items)
        plan.summary={**plan.summary,'weekly_review':result}
        print(json.dumps({'status':result['status'],'title':result['presentation']['title'],
                          'queries':[(q['id'],q['name']) for q in result['queries']]},ensure_ascii=False),flush=True)


if __name__=='__main__': main()

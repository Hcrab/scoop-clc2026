"""Restore only P8's approval state and unique test chat after browser capture.

Context and widget Undo must already have passed. This is test-fixture cleanup,
not a claim that order approval has a user-facing Undo.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from sqlalchemy import select, delete

from scoop.db import session_scope
from scoop.models import Plan, Decision, PurchaseSuggestion, WatchItem, ChatMessage
from scoop.api.service import row
from scoop.cohort_context import load_overrides


def main(context_edit):
    pid='P20260720'
    with session_scope() as session:
        context=session.get(Decision,context_edit)
        assert context and context.plan_id==pid and context.key=='set_override'
        assert context.value.get('undone_at'), 'Context Undo must succeed first'
        before=context.value['before']
        assert before['stage']=='discover'
        assert load_overrides(session)==before['overrides']
        plan=session.get(Plan,pid)
        old={r['sku']:r for r in before['orders']}
        current=list(session.scalars(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id==pid)))
        assert len(current)==len(old)==75
        def effective(r):return r['final_cases'] if r['final_cases'] is not None else r['suggested_cases']-r['capacity_cut_cases']
        for item in current:
            assert effective(row(item))==effective(old[item.sku]), 'Later quantity change; do not clean blindly'
        watches=list(session.scalars(select(WatchItem).where(WatchItem.plan_id==pid)))
        assert {w.id for w in watches}=={w['id'] for w in before['watches']}, 'Widget Undo must succeed first'
        edits=list(session.scalars(select(Decision).where(Decision.plan_id==pid,Decision.id>context_edit).order_by(Decision.id)))
        chat_edits=[e for e in edits if e.source=='chat' and e.key=='dashboard_add' and e.value.get('undone_at')]
        messages=[]
        for edit in chat_edits:
            previous={w['id'] for w in edit.value['before']['watches']}
            added=[w for w in edit.value['after']['watches'] if w['id'] not in previous]
            for widget in added:
                title=widget['title']
                if not title.startswith('Warehouse on hand '):continue
                prompt=f'Add a warehouse on-hand widget titled "{title}".'
                for message in session.scalars(select(ChatMessage).where(ChatMessage.plan_id==pid)):
                    if message.content==prompt or message.role=='assistant' and any(a.get('edit_id')==edit.id for a in (message.meta or {}).get('actions',[])):
                        messages.append(message.id)
        if messages:session.execute(delete(ChatMessage).where(ChatMessage.id.in_(messages),ChatMessage.plan_id==pid))
        for item in current:
            item.final_cases=old[item.sku]['final_cases'];item.status=old[item.sku]['status']
        summary={**plan.summary}
        if 'approved_capacity' in before['summary']:summary['approved_capacity']=before['summary']['approved_capacity']
        else:summary.pop('approved_capacity',None)
        plan.summary=summary;plan.stage=before['stage']
        plan.locked_at=datetime.fromisoformat(before['locked_at']) if before['locked_at'] else None
        for edit in edits:
            if edit.key in {'stage_approved','orders_approved'}:
                edit.value={**edit.value,'test_fixture_restore':'P8 browser capture; original stage/status restored after actual approval and Play'}
        result={'plan':pid,'context_edit':context_edit,'stage':plan.stage,'orders':len(current),
                'cases':sum(effective(r) for r in before['orders']),'widgets':len(watches),'removed_test_messages':sorted(set(messages)),
                'method':'Explicit fixture restoration from the already-undone context snapshot; context/widget Undo are separate real API checks',
                'not_a_user_approval_undo':True,'source_data_or_algorithm_changed':False}
    path=Path(f'reports/p8-fixture-cleanup-{context_edit}.json')
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--context-edit',type=int,required=True)
    main(parser.parse_args().context_edit)

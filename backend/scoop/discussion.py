"""Plan-local advisory agenda. It never writes purchasing or workflow records."""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from .models import Finding, Question


def _save(plan, items):
    plan.summary={**(plan.summary or {}),'discussion':{'items':items}}


def _items(session, plan):
    items=deepcopy((plan.summary or {}).get('discussion',{}).get('items',[]))
    changed=False
    if (plan.summary or {}).get('weekly_review',{}).get('status')=='complete':return items
    for question in session.scalars(select(Question).where(Question.plan_id==plan.id).order_by(Question.id)):
        topic_id=plan.id+'-T'+sha256(question.id.encode()).hexdigest()[:16]
        item=next((i for i in items if i['id']==topic_id),None)
        if item is None:
            finding=session.get(Finding,question.finding_id) if question.finding_id else None
            finding_id=finding.id if finding and finding.plan_id==plan.id else None
            label=(finding.evidence or {}).get('display') if finding else None
            title=question.text.strip()[:300] or ('What might explain the change in '+str(label or 'demand')+'?')
            items.append({'id':topic_id,'title':title,'status':'resolved' if question.answer is not None else 'open',
                          'finding_id':finding_id,'note':'','question_id':question.id,'managed':False})
            changed=True
        elif not item.get('managed'):
            if item['title'].startswith('Understand the change in '):
                item['title']=question.text.strip()[:300];changed=True
            status='resolved' if question.answer is not None else 'open'
            if item['status']!=status:item['status']=status;changed=True
    if changed:_save(plan,items)
    return items


def view(session, plan):
    items=_items(session,plan)
    return {'open_count':sum(i['status']=='open' for i in items),
            'items':[{key:i[key] for key in ('id','title','status','finding_id','note')} for i in items]}


def update(session, plan, args):
    # Serialize agenda updates with stage approval and other plan changes.
    session.flush()
    session.refresh(plan,with_for_update=True)
    if args.finding_id:
        finding=session.get(Finding,args.finding_id)
        if not finding or finding.plan_id!=plan.id:raise ValueError('Choose a finding from the current plan.')
    items=_items(session,plan)
    if args.operation=='add':
        title=(args.title or '').strip()
        if not title:raise ValueError('A new discussion topic needs a title.')
        if args.topic_id:raise ValueError('A new topic cannot specify an existing topic ID.')
        # Identical adds are idempotent; a resolved topic requires an explicit reopen.
        item=next((i for i in items if i['title']==title and i['finding_id']==args.finding_id),None)
        if item is None:
            item={'id':plan.id+'-T'+uuid4().hex[:16],'title':title,'status':'open',
                  'finding_id':args.finding_id,'note':args.note or '', 'managed':True}
            items.append(item)
    else:
        item=next((i for i in items if i['id']==args.topic_id),None)
        if item is None:raise ValueError('Choose a discussion topic from the current plan.')
        if args.finding_id is not None and args.finding_id!=item['finding_id']:
            raise ValueError('The topic belongs to a different finding.')
        if args.title is not None:
            if not args.title.strip():raise ValueError('A discussion title cannot be empty.')
            item['title']=args.title.strip()
        item['status']='resolved' if args.operation=='resolve' else 'open'
    if args.note is not None:item['note']=args.note.strip()
    item['managed']=True
    _save(plan,items)
    return view(session,plan)


def resolve_question(session, plan, question):
    items=_items(session,plan)
    for item in items:
        if item.get('question_id')==question.id:
            item['status']='resolved';item['managed']=True
    _save(plan,items)

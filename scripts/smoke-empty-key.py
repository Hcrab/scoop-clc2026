"""Exercise the real app with an empty key, using its in-process ASGI transport.

Run from the clean checkout with its Python/PYTHONPATH and configured isolated DB.
No HTTP response, model result or order is fabricated. No network listener is opened.
"""
import argparse
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from scoop.main import app
from scoop.config import ROOT, settings
from scoop.db import get_setting
from scoop.ai.usage import summary


def main(output):
    assert not os.environ.get('GEMINI_API_KEY'), 'Requires an actually empty key'
    before=summary()
    with TestClient(app) as client:
        def get(url):
            response=client.get(url)
            assert response.status_code==200,(url,response.status_code,response.text[:500])
            return response.json()
        health=get('/health')
        assert health['provider']=='scripted' and not health['live']
        root=client.get('/')
        assert root.status_code==200 and '<div id="root">' in root.text
        boot=get('/api/bootstrap')
        assert get_setting('seed')=='93' and boot['today']=='2026-07-20'
        assert boot['node']['capacity_pallets']==71 and len(boot['products'])==75
        endpoint='/api/plans/P20260720'
        detail=get(endpoint)
        assert len(detail['orders'])==75
        assert detail['review']['status']=='offline' and '<article data-report-card' in detail['review']['presentation']['html']
        assert '<svg' not in detail['review']['presentation']['html'].lower()
        widgets_before=get(endpoint+'/dashboard')
        reply=client.post(endpoint+'/chat',json={'message':'watch water-based demand','stage':'discover','context':{}})
        assert reply.status_code==200,reply.text[:1000]
        chat=reply.json()
        assert chat['provider']=='scripted'
        edit=next(a['edit_id'] for a in chat['actions'] if a.get('type')=='edit')
        widgets_after=get(endpoint+'/dashboard')
        assert widgets_after!=widgets_before
        undo=client.post(endpoint+f'/edits/{edit}/undo')
        assert undo.status_code==200,undo.text[:1000]
        assert get(endpoint+'/dashboard')==widgets_before
        advanced=client.post(endpoint+'/advance')
        assert advanced.status_code==200,advanced.text[:1000]
        groups=get(endpoint+'/order-summary')
        assert len(groups['groups'])>=5
    after=summary()
    assert before['calls']==after['calls']==0
    result={'checkout':str(ROOT),'configured_provider':settings.llm_provider,'key_empty':True,
            'transport':'Real FastAPI TestClient ASGI startup, no separate TCP listener',
            'health':health,'frontend_status':root.status_code,'seed':93,'week':boot['today'],
            'products':len(boot['products']),'order_rows':len(detail['orders']),
            'cohort_cards':len(detail['plan']['summary']['cohort_cards']),
            'report':'minimal offline card list','scripted_widget_edit_and_exact_undo':True,
            'orders_review':advanced.json(),'provider_calls_before':before['calls'],'provider_calls_after':after['calls']}
    Path(output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='reports/p7-empty-key-smoke.json')
    main(parser.parse_args().output)

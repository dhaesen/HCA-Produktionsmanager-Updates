from __future__ import annotations
import ast
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from patch_server import DEFAULT_SOURCE, patch_text

patched = patch_text(DEFAULT_SOURCE.read_text(encoding='utf-8'))
tree = ast.parse(patched)
names = {'_commercial_pdf_bytes','_delivery_wrap','_business_line_amounts','_document_money','_document_date','_delivery_pdf_escape'}
nodes = [node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names]
namespace = {'Any':object,'re':re,'sqlite3':sqlite3,'datetime':datetime}
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'hca-v01322-test','exec'),namespace)
namespace['_letterhead_pdf'] = lambda pages: b'\n'.join(pages)
namespace['_hca137_quote_pdf'] = lambda pages,_document: b'\n'.join(pages)

document = {
    'quote_no':'AN-TEST','created_at':'2026-09-16','totals':{'net':133.87,'tax':25.44,'gross':159.31},
    'items':[
        {'item_type':'product','sku':'ABC','description':'Artikel 1','quantity':500,'unit':'Stk.','unit_price':.2,'discount_pct':0,
         'config':{'production_steps':[{'technique':'Lasergravur','position':'Front','print_price':.03,'setup_price':13.87,'handling_price':.01}]}},
        {'item_type':'product','sku':'XYZ','description':'Artikel 2','quantity':10,'unit':'Stk.','unit_price':.5,'config':{}},
        {'item_type':'optional','description':'Alte Mengenoption','quantity':1000,'unit_price':.1,'config':{'quantity_option_generated':True}},
    ]
}
pdf_text = namespace['_commercial_pdf_bytes']('quote',document,{}).decode('cp1252','replace')
for number in ('1.1','1.2','1.3','1.4','2.1'):
    assert f'({number})' in pdf_text, f'Unterposition {number} fehlt'
assert 'Alte Mengenoption' not in pdf_text
assert 'if last_in_group:' in patched
assert 'draw_line(46,row_bottom,549,row_bottom,0.7)' in patched
print('v0.13.22 grouped document regression test passed')

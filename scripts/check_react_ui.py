"""Browser smoke check against localhost:5173 and the trusted-local full API.

Start the API and React first; install Playwright Chromium. API design/exports
use the actual backend. Requirement generation and page inspection use explicit
synthetic responses, with no provider call. Output is ignored local test data.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import json,io,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/react-ui-checks';OUT.mkdir(parents=True,exist_ok=True)
report={'processed_count':1,'extracted_count':1,'results':[{'source_id':'SOURCE-001','requirement':'A customer applies a valid coupon during checkout.','analysis':{'requirement_id':'REQ001','actor':'Customer','functionality':'Apply coupon','business_rules':['Valid coupons reduce the total by 10%'],'missing_information':['Confirm coupon expiry timezone']},'scenarios':[{'scenario_id':'SC001','requirement_id':'REQ001','title':'Apply valid coupon','scenario_type':'Functional','description':'Verify the documented discount.'}],'test_cases':[{'test_case_id':'TC001','requirement_id':'REQ001','scenario_id':'SC001','title':'Accept valid coupon','test_type':'Functional','priority':'High','steps':['Add product','Apply coupon'],'preconditions':['Cart has products'],'test_data':{'coupon':'DEMO10'},'expected_result':'Total decreases by 10%'}],'rejected_test_cases':[],'validation_summary':{'valid_test_cases':1,'invalid_test_cases':0},'validation_results':[],'evaluation':{'completeness_score':100,'traceability_score':100,'duplicate_rate':0}}]}
run={'run_id':'browser-fixture-001','status':'completed','stage':'completed','input_type':'manual','created_at':'2026-10-18T06:00:00+00:00','updated_at':'2026-10-18T06:00:00+00:00','excel_available':True,'result':report}
checks=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1060},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto('http://127.0.0.1:5173');expect(page.get_by_role('heading',name='Generate Tests from Requirements')).to_be_visible();page.screenshot(path=str(OUT/'generate-desktop.png'),full_page=True);checks.append('real full-backend capability discovery')
 page.get_by_role('link',name='API Testing',exact=True).click();page.get_by_label('Base URL',exact=True).fill('https://example.com');page.get_by_label('Required body fields',exact=True).fill('email');page.get_by_role('button',name='Design API tests').click();expect(page.get_by_role('button',name='Excel workbook')).to_be_visible(timeout=15000);page.screenshot(path=str(OUT/'api-desktop.png'),full_page=True)
 expect(page.get_by_role('button',name='Excel workbook')).to_be_disabled();page.get_by_label('I reviewed the selected test cases and their expected outcomes.').check();
 with page.expect_download() as downloaded:page.get_by_role('button',name='Excel workbook').click()
 artifact=downloaded.value;artifact.save_as(str(OUT/'api-tests.xlsx'));assert (OUT/'api-tests.xlsx').read_bytes().startswith(b'PK');checks.append('real deterministic API design, review gate and workbook export')
 page.get_by_role('link',name='Generate Tests',exact=True).click()
 def runs_route(route):
  request=route.request
  if request.method=='POST':
   body=request.post_data_json;assert body['requirement'] and body['idempotency_key'];route.fulfill(status=202,json={**run,'status':'queued','stage':'queued','result':None})
  else:route.fulfill(json={'runs':[run]})
 page.route('**/api/runs',runs_route);page.route('**/api/runs/browser-fixture-001',lambda route:route.fulfill(json=run))
 page.get_by_role('button',name='Try an example').click();page.get_by_role('button',name='Generate test cases',exact=True).click();expect(page.get_by_role('heading',name='Your test package')).to_be_visible(timeout=10000);expect(page.get_by_text('Accept valid coupon',exact=True)).to_be_visible();page.get_by_role('tab',name='Traceability',exact=True).click();expect(page.get_by_role('cell',name='REQ001',exact=True)).to_be_visible();page.screenshot(path=str(OUT/'results-desktop.png'),full_page=True);checks.append('synthetic requirement submission, polling, results and traceability')
 page.get_by_role('link',name='Run History',exact=True).click();expect(page.get_by_text('browser-fixture-001',exact=True)).to_be_visible();page.get_by_role('button',name='Open run',exact=True).click();expect(page.get_by_role('heading',name='Your test package')).to_be_visible();checks.append('saved run reopen with synthetic fixture')
 page.get_by_role('link',name='Web UI Testing',exact=True).click();assert page.locator('option[value=rendered]').evaluate('(element)=>element.disabled');checks.append('rendered capability disabled correctly')
 web={'url':'https://example.com/sign-in','page_title':'Sign in','user_goal':'View the sign-in page','snapshot':{'url':'https://example.com/sign-in','title':'Sign in','description':'Synthetic browser fixture','headings':['Sign in'],'elements':[]},'test_cases':[{'test_case_id':'WEB001','title':'Sign-in page URL is correct','objective':'Verify that the sign-in route is loaded.','test_type':'Navigation','priority':'Medium','preconditions':[],'actions':[],'assertions':[{'kind':'url_contains','value':'/sign-in','locator':None}]}]}
 page.route('**/api/web-testing/generate',lambda route:route.fulfill(json=web));page.get_by_label('Public HTTPS URL',exact=True).fill(web['url']);page.get_by_label('User goal',exact=True).fill(web['user_goal']);page.get_by_role('button',name='Inspect page & draft tests',exact=True).click();expect(page.get_by_role('button',name='Download Playwright pytest suite')).to_be_visible();expect(page.get_by_role('button',name='Download Playwright pytest suite')).to_be_disabled();page.get_by_label('I reviewed all selected actions, locators, assertions and expected outcomes.').check()
 with page.expect_download() as downloaded:page.get_by_role('button',name='Download Playwright pytest suite').click()
 downloaded.value.save_as(str(OUT/'browser-tests.zip'));assert zipfile.is_zipfile(OUT/'browser-tests.zip');checks.append('synthetic browser draft review and real backend Playwright ZIP export')
 page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='Toggle navigation').click();page.get_by_role('link',name='Generate Tests',exact=True).click();page.wait_for_function("getComputedStyle(document.querySelector('.sidebar')).visibility === 'hidden'");page.screenshot(path=str(OUT/'generate-mobile.png'),full_page=True,animations='disabled');assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page has horizontal overflow';checks.append('390px responsive layout and navigation')
 assert not errors,errors
 browser.close()
(OUT/'verification.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'generation_scope':'Synthetic browser fixtures; actual full API used for capabilities and API design/export. No AI provider call.'},indent=2))
print(json.dumps({'passed':checks,'page_errors':errors}))

import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
const root=path.resolve(import.meta.dirname,'..'),require=createRequire(path.join(root,'frontend/package.json')),ts=require('typescript')
const temporary=path.join(root,'frontend/.presentation-test.mjs')
try{
 const source=fs.readFileSync(path.join(root,'frontend/src/presentation.tsx'),'utf8')
 fs.writeFileSync(temporary,ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText)
 const {packageText,pilotConsequence,campaignChanges}=await import(pathToFileURL(temporary).href)
 const c={filter_current_tariff:'tariff_1',filter_arpu_segment:'LOW',target_tariff:'tariff_2',channel:'sms'}
 const p={campaign:{...c,channel:'digital_ads'},decision_change:{before:{plan:[c]},after:{plan:[]},selection_changed:true}}
 assert.match(pilotConsequence(p),/исключено/)
 p.decision_change.before.plan=[];p.decision_change.after.plan=[c]
 assert.match(pilotConsequence(p),/добавлено/)
 p.campaign.channel='call'
 assert.match(pilotConsequence(p),/осталось вне плана/) // independent call model
 assert.match(pilotConsequence({campaign:c}),/не записано/) // no invented archive event
 const data=packageText({price_tariff:100,Data_in_PKG:2048,Min_another_operator_in_PKG:30,Min_another_operator_and_city_in_PKG:0})
 assert.match(data,/2 ГБ/);assert.match(data,/30 мин/);assert.doesNotMatch(data,/городские/)
 const bundle=campaign=>({plan:[campaign],forecast:{details:[{contacts:100,cost:400,marginal_net:200}]}})
 const a=bundle(c),b=bundle({...c,channel:'push'}),before=JSON.stringify([a,b])
 assert.equal(campaignChanges(a,b)[0].kind,'Изменена')
 assert.equal(JSON.stringify([a,b]),before)
 assert.equal(campaignChanges(a,a).length,0)
 const absent={plan:[],forecast:{details:[]}}
 assert.equal(campaignChanges(a,absent)[0].kind,'Убрана')
 assert.equal(campaignChanges(absent,a)[0].kind,'Добавлена')
 console.log('PASS: tariff units, independent call evidence, missing traces, portfolio changes and immutability.')
}finally{if(fs.existsSync(temporary))fs.unlinkSync(temporary)}

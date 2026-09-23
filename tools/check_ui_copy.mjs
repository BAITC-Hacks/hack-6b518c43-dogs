// Parse string literals and JSX text, including the built JS bundle.
// No organizer files, raw reports or dependency source are part of this scope.
import fs from 'node:fs'
import path from 'node:path'
import {spawnSync} from 'node:child_process'
import { createRequire } from 'node:module'
const root=path.resolve(import.meta.dirname,'..')
const require=createRequire(path.join(root,'frontend/package.json'))
const ts=require('typescript')
const banned=/\b(?:LEVRA|mock|live)\b|→|—|Кампании с понятной экономикой/i
const technical=new Set(['aria-live']) // accessibility attribute name, never visible copy
const findings=[],english=[]
const files=fs.readdirSync(path.join(root,'frontend/src')).filter(n=>/\.[jt]sx?$/.test(n)).map(n=>'frontend/src/'+n)
const assets=path.join(root,'frontend/dist/assets')
if(fs.existsSync(assets))files.push(...fs.readdirSync(assets).filter(n=>n.endsWith('.js')).map(n=>'frontend/dist/assets/'+n))
for(const file of files){
 const source=fs.readFileSync(path.join(root,file),'utf8')
 const tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,file.endsWith('x')?ts.ScriptKind.TSX:ts.ScriptKind.JS)
 function visit(node){
  if(ts.isStringLiteralLike(node)||ts.isJsxText(node)){
   const value=node.text.trim()
   if(!technical.has(value)&&banned.test(value))findings.push({file,line:tree.getLineAndCharacterOfPosition(node.pos).line+1,rule:'banned-copy'})
   // Only visible JSX text is checked for untranslated developer terms.
   if(ts.isJsxText(node)&&/\b(?:dashboard|workspace|run_id|plan_id|forecast|apply|save|export|loading|replay)\b/i.test(value))
    english.push({file,line:tree.getLineAndCharacterOfPosition(node.pos).line+1,rule:'untranslated-label'})
  }
  ts.forEachChild(node,visit)
 }
 visit(tree)
}
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8')
if(banned.test(html))findings.push({file:'frontend/index.html',rule:'banned-copy'})
// Server-generated Russian explanations are also visible product copy.
const py=fs.existsSync(path.join(root,'.venv/bin/python'))?path.join(root,'.venv/bin/python'):'python3'
const scan=spawnSync(py,['-c',"import ast,json,pathlib; root=pathlib.Path('backend'); print(json.dumps([{'file':str(p),'line':n.lineno,'text':n.value} for p in root.glob('*.py') for n in ast.walk(ast.parse(p.read_text())) if isinstance(n,ast.Constant) and isinstance(n.value,str)]))"],{cwd:root,encoding:'utf8'})
if(scan.status!==0)throw new Error('Backend copy parser failed')
for(const row of JSON.parse(scan.stdout))if(!technical.has(row.text)&&banned.test(row.text))findings.push({file:row.file,line:row.line,rule:'banned-server-copy'})
const report={passed:findings.length===0&&english.length===0,scope:'Frontend JSX text and string literals; generated JS string literals; HTML; backend string literals. Only aria-live attribute is exempt.',files:files.length,findings,english}
fs.mkdirSync(path.join(root,'reports/stage4'),{recursive:true})
fs.writeFileSync(path.join(root,'reports/stage4/copy_lint.json'),JSON.stringify(report,null,2))
console.log(JSON.stringify(report,null,2))
if(!report.passed)process.exitCode=1

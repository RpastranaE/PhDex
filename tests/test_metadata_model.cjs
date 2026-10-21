const {test}=require('node:test');
const assert=require('node:assert/strict');
const model=require('../web/metadata-model.js');

test('files start independently without a shared record or scientific numbering',()=>{
  const a=model.fresh('2026-10-21'),b=model.fresh('2026-10-21');
  const edited=model.change(a,'owner_code','exp-702');
  assert.equal(edited.owner_kind,'experiment');
  assert.equal(edited.owner_code,'EXP-702');
  assert.equal(b.owner_code,'');assert.equal(a.owner_code,'');
  assert.equal(b.category,'');assert.equal(b.version,0);
});
test('bulk application copies only explicitly checked fields',()=>{
  const current={...model.fresh('2026-10-21'),category:'photo',owner_kind:'sample',owner_code:'MUE-703',content:'Foto'};
  const result=model.apply(current,{date:'2026-10-20',owner_code:'CAR-701',content:'Espectro'},['date']);
  assert.equal(result.date,'2026-10-20');assert.equal(result.owner_code,'MUE-703');assert.equal(result.content,'Foto');
  assert.equal(current.date,'2026-10-21');
});
test('changing raw type resets version and independence confirmation',()=>{
  const current={...model.fresh('2026-10-21'),version:4,independent_raw:true};
  const raw=model.change(current,'category','raw_copy','characterization');
  assert.equal(raw.version,0);assert.equal(raw.independent_raw,false);
  assert.equal(raw.owner_kind,'characterization');
});
test('bulk type changes cannot silently confirm raw independence',()=>{
  const current={...model.fresh('2026-10-21'),independent_raw:true};
  const raw=model.apply(current,{category:'raw_copy',version:8,independent_raw:true},['category','version']);
  assert.equal(raw.version,0);assert.equal(raw.independent_raw,false);
});
test('category defaults preserve a record already chosen for that file',()=>{
  const current={...model.fresh('2026-10-21'),owner_kind:'result',owner_code:'RES-704'};
  const next=model.change(current,'category','processed','characterization');
  assert.equal(next.owner_kind,'result');assert.equal(next.owner_code,'RES-704');
});

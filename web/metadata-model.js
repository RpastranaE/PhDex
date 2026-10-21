'use strict';
(function(root) {
  const kinds={CAR:'characterization',EXP:'experiment',MUE:'sample',RES:'result'};
  function fresh(date) {
    return {category:'',owner_kind:'',owner_code:'',date,content:'',technique:'',samples:'',
      replicate:0,version:0,experiments:'',characterizations:'',note:'',independent_raw:false};
  }
  function change(meta,field,value,categoryOwner='') {
    const result={...meta,[field]:value};
    if(field==='owner_code') {
      result.owner_code=String(value).trim().toUpperCase();
      const match=result.owner_code.match(/^([A-Z]+)-/);
      if(match)result.owner_kind=kinds[match[1]]||'other';
    }
    if(field==='category') {
      if(!result.owner_kind&&categoryOwner)result.owner_kind=categoryOwner;
      if(String(value).startsWith('raw_'))result.version=0;
      result.independent_raw=false;
    }
    return result;
  }
  function apply(meta,values,fields) {
    // Aplicación explícita: no heredar otros campos del formulario conjunto.
    const result={...meta};
    for(const field of fields)if(Object.hasOwn(values,field))result[field]=values[field];
    if(result.category.startsWith('raw_'))result.version=0;
    if(fields.includes('category'))result.independent_raw=false;
    return result;
  }
  const api={fresh,change,apply};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.MetadataModel=api;
})(typeof window==='undefined'?globalThis:window);

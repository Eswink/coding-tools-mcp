/** Numeric contrast of the actual semantic tokens; not a whole-page WCAG audit. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const css=readFileSync(new URL('../src/lib/styles/tokens.css',import.meta.url),'utf8');
function tokens(dark){const blocks=[...css.matchAll(/\{([^{}]+)\}/g)].map(match=>Object.fromEntries([...match[1].matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(m=>[m[1],m[2].trim()])));return {...blocks[0],...(dark?blocks[1]:{})};}
function color(tokens,key){let value=tokens[key]??key;for(let i=0;i<5 && value.startsWith('var(');i++)value=tokens[value.slice(4,-1)];assert.match(value,/^#[0-9a-f]{6}$/i,`${key} must resolve to an opaque semantic color`);return value;}
function luminance(hex){const channels=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;}
function ratio(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
for(const dark of [false,true])test(`${dark?'dark':'light'} enabled semantic text and actions meet 4.5:1`,()=>{
  const t=tokens(dark);
  for(const [fg,bg] of [['--text-main','--card-bg'],['--text-secondary','--card-bg'],['--text-muted','--card-bg'],['--primary','--card-bg'],['--success','--success-soft'],['--warning','--warning-soft'],['--primary-foreground','--action-bg'],['--primary-foreground','--danger-bg']]){
    // Before the fix destructive buttons directly used the light red text token.
    const background=bg==='--danger-bg' && !t[bg]?'--danger':bg;
    const actual=ratio(color(t,fg),color(t,background));assert.ok(actual>=4.5,`${fg} on ${background}: ${actual.toFixed(2)}:1`);
  }
});

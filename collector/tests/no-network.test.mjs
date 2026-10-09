import test from 'node:test';
import assert from 'node:assert/strict';
import dns from 'node:dns';
import {Resolver as PromiseResolver} from 'node:dns/promises';

// Check identity before calling so a removed guard cannot turn this regression
// into a real DNS canary. Exercise callback, promise and inherited methods.
for(const [kind,Resolver] of [['callback',dns.Resolver],['promise',PromiseResolver]]){
  for(const method of ['resolve','resolve4','resolve6','resolveAny','resolveCaa','resolveCname',
      'resolveMx','resolveNaptr','resolveNs','resolvePtr','resolveSoa','resolveSrv','resolveTxt','reverse']){
    test(`${kind} independent resolver refuses ${method} before dispatch`,()=>{
      const resolver=new Resolver();
      assert.equal(resolver[method],dns.resolve4);
      assert.throws(()=>resolver[method]('synthetic.invalid',()=>{}),/^Error: TEST_NETWORK_FORBIDDEN$/);
    });
  }
}

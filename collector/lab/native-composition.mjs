// Development-only factory; default broker exports cannot select this policy.
import {syntheticPolicy} from '../internal/source-policy.mjs';
import {authorityForPolicy} from '../core.mjs';
import {controllerForPolicy} from '../request-controller.mjs';

export function nativeComposition(origin, allocation) {
  const policy = syntheticPolicy(origin, allocation), authority = authorityForPolicy(policy);
  function controller(handle, options) {
    authority.assertHandle(handle);
    if (!options || Object.hasOwn(options, 'consume') || Object.hasOwn(options, 'policy')) {
      throw new Error('REQUEST_CONFIG_INVALID');
    }
    return controllerForPolicy(policy, {...options,
      consume: (request, time) => authority.consumePermit(handle, request, time)});
  }
  return Object.freeze({...authority, controller});
}

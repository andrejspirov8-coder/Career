import { describe, expect, it } from 'vitest';
import { verifyDashboardSession } from './session';

describe('verifyDashboardSession', () => {
  it('should reject un-signed or plain text session cookies', () => {
    const secret = '0123456789abcdef0123456789abcdef';
    const session = verifyDashboardSession('plain-text-cookie-without-sig', secret);
    expect(session).toBeNull();
  });
});

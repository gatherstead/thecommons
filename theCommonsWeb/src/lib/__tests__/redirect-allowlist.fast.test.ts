import { describe, expect, it } from 'vitest';
import { resolveRedirect } from '../redirect-allowlist';

describe('resolveRedirect', () => {
    describe('accepts', () => {
        it('the apex thecommons.town origin', () => {
            expect(resolveRedirect('https://thecommons.town/dashboard')).toBe(
                'https://thecommons.town/dashboard',
            );
        });

        it('the www subdomain', () => {
            expect(resolveRedirect('https://www.thecommons.town/profile')).toBe(
                'https://www.thecommons.town/profile',
            );
        });

        it('arbitrary thecommons.town subdomains', () => {
            expect(
                resolveRedirect('https://broadcast.thecommons.town/events'),
            ).toBe('https://broadcast.thecommons.town/events');
            expect(resolveRedirect('https://auth.thecommons.town/login')).toBe(
                'https://auth.thecommons.town/login',
            );
        });

        it('localhost on any port over http or https (dev only)', () => {
            expect(resolveRedirect('http://localhost:5173/foo')).toBe(
                'http://localhost:5173/foo',
            );
            expect(resolveRedirect('https://localhost:3000/foo')).toBe(
                'https://localhost:3000/foo',
            );
        });

        it('127.0.0.1 on any port', () => {
            expect(resolveRedirect('http://127.0.0.1:8000/foo')).toBe(
                'http://127.0.0.1:8000/foo',
            );
        });

        it('same-origin relative paths unchanged', () => {
            expect(resolveRedirect('/dashboard')).toBe('/dashboard');
            expect(resolveRedirect('/profile#digest')).toBe('/profile#digest');
        });
    });

    describe('rejects (returns fallback)', () => {
        it('protocol-relative URLs', () => {
            expect(resolveRedirect('//evil.com')).toBe('/');
        });

        it('non-http(s) schemes', () => {
            expect(resolveRedirect('javascript:alert(1)')).toBe('/');
            expect(resolveRedirect('data:text/html,<script>alert(1)</script>')).toBe(
                '/',
            );
            expect(resolveRedirect('mailto:foo@evil.com')).toBe('/');
        });

        it('suffix-spoof hosts', () => {
            expect(resolveRedirect('https://thecommons.town.evil.com')).toBe('/');
            expect(resolveRedirect('https://notthecommons.town')).toBe('/');
        });

        it('userinfo tricks', () => {
            expect(resolveRedirect('https://user@evil.com')).toBe('/');
            expect(resolveRedirect('https://thecommons.town@evil.com')).toBe('/');
        });

        it('null, undefined, empty, and whitespace-only input', () => {
            expect(resolveRedirect(null)).toBe('/');
            expect(resolveRedirect(undefined)).toBe('/');
            expect(resolveRedirect('')).toBe('/');
            expect(resolveRedirect('   ')).toBe('/');
        });

        it('unparseable input', () => {
            expect(resolveRedirect('not a url at all :::')).toBe('/');
        });

        it('http (non-https) for thecommons.town hosts', () => {
            expect(resolveRedirect('http://thecommons.town/dashboard')).toBe('/');
        });
    });

    describe('fallback behavior', () => {
        it('returns the fallback instead of throwing', () => {
            expect(() => resolveRedirect('javascript:alert(1)')).not.toThrow();
        });

        it('honors a custom fallback argument', () => {
            expect(resolveRedirect('https://evil.com', '/safe-landing')).toBe(
                '/safe-landing',
            );
            expect(resolveRedirect(null, '/safe-landing')).toBe('/safe-landing');
        });

        it('defaults the fallback to "/"', () => {
            expect(resolveRedirect('https://evil.com')).toBe('/');
        });
    });
});

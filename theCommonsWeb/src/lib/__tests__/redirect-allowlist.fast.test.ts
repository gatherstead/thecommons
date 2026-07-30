import { describe, expect, it } from 'vitest';
import { resolveRedirect } from '../redirect-allowlist';

describe('resolveRedirect', () => {
    it('accepts an https subdomain of thecommons.town unchanged', () => {
        expect(resolveRedirect('https://broadcast.thecommons.town/x')).toBe(
            'https://broadcast.thecommons.town/x',
        );
    });

    it('accepts the apex and www hosts', () => {
        expect(resolveRedirect('https://thecommons.town/dashboard')).toBe(
            'https://thecommons.town/dashboard',
        );
        expect(resolveRedirect('https://www.thecommons.town/dashboard')).toBe(
            'https://www.thecommons.town/dashboard',
        );
    });

    it('accepts another subdomain, e.g. auth.thecommons.town', () => {
        expect(resolveRedirect('https://auth.thecommons.town/callback')).toBe(
            'https://auth.thecommons.town/callback',
        );
    });

    it('falls back for an unrelated domain', () => {
        expect(resolveRedirect('https://evil.com')).toBe('/');
    });

    it('rejects protocol-relative URLs', () => {
        expect(resolveRedirect('//evil.com')).toBe('/');
    });

    it('rejects javascript: scheme', () => {
        expect(resolveRedirect('javascript:alert(1)')).toBe('/');
    });

    it('rejects data: scheme', () => {
        expect(resolveRedirect('data:text/html,<script>alert(1)</script>')).toBe('/');
    });

    it('rejects lookalike domains that merely end in thecommons.town as a substring', () => {
        expect(resolveRedirect('https://thecommons.town.evil.com')).toBe('/');
    });

    it('rejects userinfo tricks', () => {
        expect(resolveRedirect('https://user@evil.com')).toBe('/');
        expect(resolveRedirect('https://user@thecommons.town')).toBe('/');
    });

    it('accepts localhost on any port, http or https', () => {
        expect(resolveRedirect('http://localhost:5173/foo')).toBe('http://localhost:5173/foo');
        expect(resolveRedirect('https://localhost:5173/foo')).toBe('https://localhost:5173/foo');
        expect(resolveRedirect('http://127.0.0.1:8000/bar')).toBe('http://127.0.0.1:8000/bar');
    });

    it('accepts a same-origin relative path as-is', () => {
        expect(resolveRedirect('/dashboard')).toBe('/dashboard');
    });

    it('falls back for null or empty input', () => {
        expect(resolveRedirect(null)).toBe('/');
        expect(resolveRedirect('')).toBe('/');
    });

    it('respects a custom fallback', () => {
        expect(resolveRedirect(null, '/login')).toBe('/login');
        expect(resolveRedirect('https://evil.com', '/login')).toBe('/login');
    });

    it('rejects malformed input without throwing', () => {
        expect(() => resolveRedirect('http://')).not.toThrow();
        expect(resolveRedirect('http://')).toBe('/');
    });
});

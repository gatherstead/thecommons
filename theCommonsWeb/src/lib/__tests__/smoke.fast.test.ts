import { describe, expect, it } from 'vitest';

describe('fast tier smoke', () => {
    it('runs pure assertions without a DOM', () => {
        expect(1 + 1).toBe(2);
        expect(typeof window).toBe('undefined');
    });
});
